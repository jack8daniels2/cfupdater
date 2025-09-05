#### CF Updater

1. Query host's external IP address using Cloudflare Speed test
2. Update Cloudflare DNS record that is extracted from OnePassword
3. Verify DNS record

### How to run
1. docker build -t cfupdate:latest .
2. docker run --rm -e OP_SERVICE_ACCOUNT_TOKEN=$(op read op://Private/iefpj5o6rieaog5mujyfa77kqy/credential) cfupdate
