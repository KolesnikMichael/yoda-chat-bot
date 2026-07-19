# TASK-008 implementation notes

## Corporate TLS MITM (Kaspersky) — pip CA trust

PyPI HTTPS from WSL failed with `SSLCertVerificationError: unable to get local issuer certificate`.
Leaf presented to Python was issued by **`CN=Generic Root CA 3, C=EN`** (Kaspersky SSL inspection), not GlobalSign.
OpenSSL `s_client` sometimes showed the public chain; Python/certifi saw the MITM leaf.

### Extracted from Windows cert stores (`LocalMachine\Root` / `CurrentUser\Root`)

| Cert | Role |
|------|------|
| `Generic Root CA 3` | Issuer of MITM leaf for pypi.org / pythonhosted.org |
| `Kaspersky Endpoint Security Personal Certification Authority` | Kaspersky product CA |
| Amdocs Corporate / Global / Root / Class 3 / Enrollment | Corporate roots (included for other HTTPS) |

### Permanent `.venv` trust (local machine)

1. Bundle: `.certs/corp-ca-bundle.pem` = certifi cacert + corp PEMs (gitignored).
2. `.venv/pip.conf` → `[global] cert = <abs-path>/.certs/corp-ca-bundle.pem`
3. `.venv/bin/activate` exports `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`, `PIP_CERT` to the same bundle.

After that, `pip install chromadb` into `.venv` succeeds (no `--trusted-host`).

Secondary issue: `.venv` had a symlink `yaml → /usr/lib/python3/dist-packages/yaml`; removed so PyYAML could install into the venv.

Temporary `vendor/chromadb_deps` + import shims in `vector.py` / `conftest.py` removed after `chromadb` landed in `.venv` via the CA bundle.

## AST import guard refined

TASK-004 guard forbade any import containing `embedding` / `vector`, which blocked required Provider injection (`yoda.mind.memory.embedding`, `yoda.mind.memory.vector`). Test updated to forbid only `yoda.api.embeddings_api` and `chromadb` imports in `maintenance.py`.

## IODA: metadata flatten lives on VectorProvider

`VectorProvider` flattens `ChromaSummaryRecord` lists (`skills`/`topics`) via a private
`_flatten_metadata` adapter method. `SummaryStoreCore.flatten_metadata` remains the
outbox-entry helper used by Core consumers/tests. Provider must not import Core
(Operations never depend on other Operations).

## Follow-up (in scope notes)

Chroma collection drop on `delete_user_data` deferred per design Decision 11 → [[TASK-013-chroma-drop-on-delete-user-data/task|TASK-013]].
