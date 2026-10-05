"""Small persistent adapters. JSON payloads keep DynamoDB numeric conversion simple."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError


class BusyError(Exception):
    pass


class LocalRepository:
    def __init__(self, root: Path, experiment: str):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / f"{experiment}.sqlite3"
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS locks (id TEXT PRIMARY KEY, token TEXT, expires REAL)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def get(self, key: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM records WHERE id=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, value: dict) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO records VALUES (?, ?)", (key, json.dumps(value)))

    def list(self, prefix: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT id, payload FROM records ORDER BY id").fetchall()
        return [json.loads(payload) for key, payload in rows if key.startswith(prefix)]

    def delete(self, key: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM records WHERE id=?", (key,))

    def acquire(self, key: str, seconds: int = 900) -> str:
        token = uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT expires FROM locks WHERE id=?", (key,)).fetchone()
            if row and row[0] > time.time():
                raise BusyError("Another operation is in progress; try again shortly")
            db.execute("INSERT OR REPLACE INTO locks VALUES (?, ?, ?)", (key, token, time.time() + seconds))
        return token

    def owns(self, key: str, token: str) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT token, expires FROM locks WHERE id=?", (key,)).fetchone()
        return bool(row and row[0] == token and row[1] > time.time())

    def release(self, key: str, token: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM locks WHERE id=? AND token=?", (key, token))


class DynamoRepository:
    def __init__(self, table: str, experiment: str, region: str):
        self.table = boto3.resource("dynamodb", region_name=region).Table(table)
        self.pk = experiment

    def get(self, key: str) -> dict | None:
        item = self.table.get_item(Key={"pk": self.pk, "sk": key}, ConsistentRead=True).get("Item")
        return json.loads(item["payload"]) if item else None

    def put(self, key: str, value: dict) -> None:
        self.table.put_item(Item={"pk": self.pk, "sk": key, "payload": json.dumps(value)})

    def list(self, prefix: str) -> list[dict]:
        kwargs = {"KeyConditionExpression": Key("pk").eq(self.pk) & Key("sk").begins_with(prefix), "ConsistentRead": True}
        result = []
        while True:
            page = self.table.query(**kwargs)
            result.extend(json.loads(item["payload"]) for item in page["Items"])
            if "LastEvaluatedKey" not in page:
                return result
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def delete(self, key: str) -> None:
        self.table.delete_item(Key={"pk": self.pk, "sk": key})

    def acquire(self, key: str, seconds: int = 900) -> str:
        token = uuid4().hex
        try:
            self.table.put_item(
                Item={"pk": self.pk, "sk": "lock#" + key, "token": token, "expires": int(time.time()) + seconds},
                ConditionExpression="attribute_not_exists(pk) OR expires < :now",
                ExpressionAttributeValues={":now": int(time.time())},
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise BusyError("Another operation is in progress; try again shortly") from error
            raise
        return token

    def owns(self, key: str, token: str) -> bool:
        item = self.table.get_item(Key={"pk": self.pk, "sk": "lock#" + key}, ConsistentRead=True).get("Item", {})
        return item.get("token") == token and item.get("expires", 0) > time.time()

    def release(self, key: str, token: str) -> None:
        try:
            self.table.delete_item(Key={"pk": self.pk, "sk": "lock#" + key}, ConditionExpression="#t = :token", ExpressionAttributeNames={"#t": "token"}, ExpressionAttributeValues={":token": token})
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise


@contextmanager
def locked(repository, key: str):
    token = repository.acquire(key)
    try:
        yield token
    finally:
        repository.release(key, token)


class LocalObjects:
    def __init__(self, root: Path):
        self.root = root / "objects"
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if not target.is_relative_to(self.root.resolve()):
            raise ValueError("Invalid object key")
        return target

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + "." + uuid4().hex)
        temporary.write_bytes(data)
        temporary.replace(path)

    def get(self, key: str, limit: int = 50 * 1024 * 1024) -> bytes:
        path = self.path(key)
        if path.stat().st_size > limit:
            raise ValueError("Image exceeds upload size limit")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> None:
        for path in self.path(prefix).glob("**/*"):
            if path.is_file():
                path.unlink()


class S3Objects:
    def __init__(self, bucket: str, region: str):
        self.bucket = bucket
        self.client = boto3.client("s3", region_name=region)

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str, limit: int = 50 * 1024 * 1024) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        try:
            if response["ContentLength"] > limit:
                raise ValueError("Image exceeds upload size limit")
            return response["Body"].read(limit + 1)
        finally:
            response["Body"].close()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def delete_prefix(self, prefix: str) -> None:
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
            keys = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if keys:
                response = self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": keys})
                if response.get("Errors"):
                    raise RuntimeError("Some objects could not be deleted; retry cleanup")

    def upload(self, key: str, content_type: str, limit: int) -> dict:
        # POST enforces the size limit at S3, unlike an unrestricted presigned PUT.
        return self.client.generate_presigned_post(
            self.bucket, key, Fields={"Content-Type": content_type},
            Conditions=[{"Content-Type": content_type}, ["content-length-range", 1, limit]], ExpiresIn=300,
        )
