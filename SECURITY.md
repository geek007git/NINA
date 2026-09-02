# Security

## Reporting

Open a private security advisory on the GitHub repository, or contact the
maintainer directly. Please do not open a public issue for a vulnerability.

## Credentials

NINA reads all secrets from the environment. Never commit a `.env` — it is in
`.gitignore`, and `nina doctor` redacts every secret before printing config.

### Rotate the keys that were committed to this repository

An early commit in this repository's history (`81e80c1`) contained a real `.env`
with a live LiveKit API key and secret and a Google API key. The file was deleted
in a later commit, **but deleting a file does not remove it from git history** —
anyone who clones the repository can still read those values.

If they have not already been rotated:

1. Revoke and reissue the LiveKit API key and secret at
   <https://cloud.livekit.io> (project settings → Keys).
2. Revoke and reissue the Google API key at <https://aistudio.google.com/apikey>.
3. Optionally purge the blob from history with
   [git-filter-repo](https://github.com/newren/git-filter-repo) and force-push.
   Rotation is what actually protects you; purging only limits further exposure.

## Notes

- The memory store at `NINA_MEMORY_PATH` holds whatever a user asked NINA to
  remember, in plaintext JSON. Treat it as personal data: it is gitignored by
  default, and it should not be committed or shipped inside an image.
- Tool output is model-controlled text spoken back to the user. It is never
  executed, and no tool in this repository runs shell commands, reads arbitrary
  files, or writes anywhere except the configured memory path.
