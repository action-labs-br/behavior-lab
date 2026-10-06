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

if (bundledVersion === patchedVersion) {
  console.log(`aws-cdk-lib already bundles brace-expansion ${patchedVersion}`);
} else {
  await rm(bundledPackage, { recursive: true, force: true });
  await cp(patchedPackage, bundledPackage, { recursive: true });
  console.log(
    `Replaced aws-cdk-lib's bundled brace-expansion ${bundledVersion} with ${patchedVersion}`,
  );
}
