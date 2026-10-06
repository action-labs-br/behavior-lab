# GitHub Dependabot remediation plan

Snapshot date: 2026-10-06
Repository: `gdesouza/ml-sandbox`
Source: [open Dependabot alerts](https://github.com/gdesouza/ml-sandbox/security/dependabot)

## Findings

GitHub reports **21 open alerts**. They represent **three advisories against one vulnerable transitive package**, `brace-expansion`, rather than 21 independent dependency updates. All alerts are npm runtime dependencies in the Behavior Cloning Game CDK dependency tree.

| Severity | Advisory | Issue | First patched version reported by GitHub |
| --- | --- | --- | --- |
| High | [GHSA-6j4f-fj2g-mc7p](https://github.com/advisories/GHSA-6j4f-fj2g-mc7p) | Stack exhaustion in `parseCommaParts` can crash Node.js | 5.0.10 |
| High | [GHSA-qhr7-859c-m2p7](https://github.com/advisories/GHSA-qhr7-859c-m2p7) | Deeply nested brace groups can exhaust the stack | 5.0.11 |
| Medium | [GHSA-q2hr-2g5m-vwhr](https://github.com/advisories/GHSA-q2hr-2g5m-vwhr) | Pathological brace input causes quadratic CPU use | 5.0.12 |

GitHub finds each advisory in the current lockfile at `projects/behavior-cloning-game/infra/cdk/package-lock.json` and in six `infra/cdk/cdk.out/asset.*/infra/cdk/package-lock.json` snapshots. That is seven manifests per advisory (21 alert records). The original source lockfile resolved `aws-cdk-lib`'s bundled `brace-expansion` to **5.0.9**, below every patched version. The package is transitive and marked `inBundle` in the lockfile. The latest available `aws-cdk-lib` in this workspace also bundles 5.0.9, and bundled dependencies cannot be repaired by npm overrides.

## Remediation sequence

1. **Patch the bundled dependency at install time.** Because no available `aws-cdk-lib` release supplies the patched bundle, add `brace-expansion@5.0.12` as a CDK development dependency. A `postinstall` script replaces an older nested bundled copy, preserves any stable bundled version at or above 5.0.12, and fails if the expected package layout or version format changes. The lockfile records the repaired nested version so dependency scanners inspect the effective version.
2. **Keep synthesized output out of Git.** Remove the six flagged `infra/cdk/cdk.out/asset.*` snapshots, which were generated CDK output containing copied source and lockfiles, and ignore `infra/cdk/cdk.out/` at the repository root. The active project's `.gitignore` already excludes its own synthesis output.
3. **Validate fresh installs and synthesis.** From `projects/behavior-cloning-game/infra/cdk`, run `npm ci`, confirm both `npm ls brace-expansion --all` and the nested installed package report 5.0.12, run `npm audit`, and run CDK synthesis. Review the template diff for unrelated infrastructure changes.
4. **Confirm GitHub closure.** Once this branch reaches the default branch, refresh Dependabot and verify all three advisories close across the active manifest and that the stale generated paths are gone. Do not dismiss the alerts as risk acceptance; these are availability issues.

## Priority and completion criteria

Address the two **High** stack exhaustion advisories first, but ship one dependency resolution that also reaches **5.0.12** and closes the Medium CPU denial-of-service advisory. Treat all three as one remediation unit. Completion means the canonical dependency tree and CDK's nested installed copy resolve to `brace-expansion >=5.0.12`, clean installs apply the repair, obsolete snapshots are no longer tracked, and GitHub shows no open alerts for these advisories.

## Compatibility checks / risks

- The vulnerable package is bundled beneath `aws-cdk-lib`; upgrading only the top-level CDK CLI is unlikely to change its resolution. The install-time repair is a workaround until upstream publishes a fixed bundle. Remove the repair when the upstream copy is at least 5.0.12.
- The repair depends on the current nested package path. It validates the path and version and will fail loudly if a future `aws-cdk-lib` changes its bundle layout.
- Updating `aws-cdk-lib` can change synthesized CloudFormation output. Review the template diff and run the documented CDK synthesis before merging.
- The generated snapshots were tracked despite being CDK output. They are removed from this branch after confirming no deployment or release scripts consume them.
