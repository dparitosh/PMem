# Dependency and footprint remediation

31 October 2026. Scope: default and isolated Python locks, installed package
metadata, checkout caches, customer package selection and the page/session audit.

## Confirmed reduction

The default runtime lock contained nine packages outside the exact dependency
closure of `backend/requirements.txt`: `imageio`, `ninja`,
`opencv-python-headless`, `pyclipper`, `python-bidi`, `scikit-image`, `shapely`,
`tifffile`, and `torchvision`. These are dependencies of optional EasyOCR.
Their existing pins/hashes moved to the OCR overlay. Default closure: **199 to
190 distributions** (4.5% fewer pinned packages). OCR remains available.

Local installed RECORD metadata totals these nine entries at 153,523,561 bytes
(146.4 MiB). This is **not physical disk savings**: OpenCV packages describe
overlapping files. No live packages were uninstalled. Reused customer runtimes
retain old packages; a planned fresh locked environment is required to realize
the smaller footprint safely.

The installed deployment contains only `.dt_venv`, so there are no per-service
runtime copies to deduplicate there. Shared mode already reuses dependencies.
Isolated mode deliberately retains service-specific environments. Their existing
closed dependency profiles remain unchanged, avoiding shared writable package
directories and cross-service upgrades.

## Packages retained

Torch, Transformers, spaCy, SciPy, plotting/notebook support and embedding
libraries are declared dependencies of the pinned Semantica release. Absence of
direct PMem imports is not evidence they can be uninstalled. Reducing that set
requires upstream-supported dependency separation and semantic-runtime testing.
No `--no-deps` workaround was added.

The installed environment also has pytest, pytest-asyncio, iniconfig and pluggy
outside the production lock. They support current acceptance testing and remain
in that local test environment. They are not selected for a fresh standard
customer install. Pip is installation tooling and remains necessary.

## Cleanup and release changes

- Removed 15,559,081 bytes (14.8 MiB) of reproducible checkout caches using the
  new allowlisted maintenance tool. Preserved data, uploads, logs, environments,
  served assets and audit evidence. Exact receipts are local in `outputs/`.
- Added a read-only runtime-footprint report; size labels explicitly describe
  RECORD accounting and do not claim physical usage or uninstall safety.
- Release packaging excludes generated audit JSON/XML/images/HTML and caches.
  It preserves source mapping JSON and foundation manifests. Existing retained
  artifacts remain governed by Admin retention rather than filesystem deletion.
- Added dependency-closure, protected-path cleanup and release-selection tests.
- Fixed frontend build publication after live testing found that rebuilding
  removed lazy chunks needed by an open browser tab. Staging now preserves old
  hashed assets and replaces the served index last. Old assets remain outside
  the cache deletion allowlist.

## Page/session fixes

Products now refreshes on delegation replacement and expiry and rejects an old
run response through its generation guard. Product discovery does not render
false empty records during initial loading. Registry distinguishes loading
from unavailability, removes its duplicate title and updates lifecycle guidance.
Publication-access instructions distinguish scoped writes from maintenance.
The XML loader invalidates on expiry as well as replacement. Health responses
must explicitly report a recognized positive status instead of accepting any
successful HTTP response. These changes do not establish full customer
acceptance or per-capability readiness.

## Validation

- Dependency closure, service profile locks, optional OCR and package-selection
  checks: 10 passed after regenerating the package-count report's missing final
  newline. No service dependency versions or generated locks changed.
- Targeted Products/Registry/XML loader tests: 38 passed.
- Full frontend suite: 826 passed across 135 files. Final page/health selection:
  54 passed. Staged build success/failure integration tests: 2 passed.
- Production frontend builds passed, including the local deployed build. Full
  customer acceptance remains separate from local verification.

No LLM service was used or required for these changes.
