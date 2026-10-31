# Prebuilt DocWeave dev image: the devcontainer base with a ready Frappe bench
# (Frappe and ERPNext at the tags pinned in post-create.sh) in
# /home/vscode/frappe-bench. No site and no database: those are created when
# the container starts (onCreateCommand), against the Compose MariaDB.
#
# Built and published by .github/workflows/dev-image.yml. A new frappe-bench
# volume is seeded from this image's bench, so setup skips bench init and
# get-app.

# Same base and digest as docker-compose.yml used before the image existed.
FROM mcr.microsoft.com/devcontainers/base:ubuntu26.04@sha256:91eff046d5c12318fc98e59258982b87ba896c467427ed8b5dab5a02107a5db7

# bench init and get-app need Node and Yarn. The devcontainer Node feature is
# applied only when the container is created, not during docker build.
ARG NODE_VERSION=24.22.1
ARG YARN_VERSION=1.22.22
RUN set -eux; \
    cd /tmp; \
    tarball="node-v${NODE_VERSION}-linux-x64.tar.xz"; \
    curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/${tarball}"; \
    curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt"; \
    grep " ${tarball}\$" SHASUMS256.txt | sha256sum -c -; \
    tar -xJf "${tarball}" -C /usr/local --strip-components=1 --no-same-owner; \
    rm -f "${tarball}" SHASUMS256.txt; \
    npm install -g "yarn@${YARN_VERSION}"; \
    node --version; \
    yarn --version

USER vscode
COPY --chown=vscode:vscode post-create.sh /tmp/post-create.sh
# System packages, uv, Python, frappe-bench, bench init and ERPNext. The script
# stops before anything that needs MariaDB or Redis.
RUN DOCWEAVE_STAGE=image bash /tmp/post-create.sh \
    && rm /tmp/post-create.sh \
    && sudo rm -rf /var/lib/apt/lists/* \
    && rm -rf /home/vscode/.cache/uv /home/vscode/.cache/yarn /home/vscode/.npm

USER root
