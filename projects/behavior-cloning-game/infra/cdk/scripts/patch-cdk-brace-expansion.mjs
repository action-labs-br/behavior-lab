import { cp, readFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';

const patchedPackage = resolve('node_modules/brace-expansion');
const bundledPackage = resolve(
  'node_modules/aws-cdk-lib/node_modules/brace-expansion',
);

const readVersion = async (packagePath) => {
  const packageJson = JSON.parse(
    await readFile(resolve(packagePath, 'package.json'), 'utf8'),
  );
  return packageJson.version;
};

const isPatchedVersion = (version) => {
  const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(version);
  if (!match) {
    throw new Error(`Unexpected brace-expansion version format: ${version}`);
  }

  const [, major, minor, patch] = match.map(Number);
  return (
    major > 5 ||
    (major === 5 && minor > 0) ||
    (major === 5 && minor === 0 && patch >= 12)
  );
};

const patchedVersion = await readVersion(patchedPackage);
if (patchedVersion !== '5.0.12') {
  throw new Error(
    `Expected brace-expansion 5.0.12, found ${patchedVersion} at ${patchedPackage}`,
  );
}

let bundledVersion;
try {
  bundledVersion = await readVersion(bundledPackage);
} catch (error) {
  if (error.code === 'ENOENT') {
    throw new Error(
      `Expected aws-cdk-lib's bundled brace-expansion at ${bundledPackage}`,
    );
  }
  throw error;
}

if (isPatchedVersion(bundledVersion)) {
  console.log(
    `aws-cdk-lib already bundles patched brace-expansion ${bundledVersion}`,
  );
} else {
  await rm(bundledPackage, { recursive: true, force: true });
  await cp(patchedPackage, bundledPackage, { recursive: true });
  console.log(
    `Replaced aws-cdk-lib's bundled brace-expansion ${bundledVersion} with ${patchedVersion}`,
  );
}
