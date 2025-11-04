FROM mcr.microsoft.com/devcontainers/python:1-3.11-bookworm

ENV PYTHONUNBUFFERED 1

RUN mkdir -p /workspace/Server && chown -hR vscode /workspace

USER vscode

COPY Server/requirements.txt /tmp/pip-tmp/
RUN --mount=type=cache,target=/root/.cache/pip pip3 --disable-pip-version-check install -r /tmp/pip-tmp/requirements.txt \
   && sudo rm -rf /tmp/pip-tmp

RUN export DEBIAN_FRONTEND=noninteractive && wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add - \
    && echo "deb http://apt.postgresql.org/pub/repos/apt/ `lsb_release -cs`-pgdg main" | sudo tee /etc/apt/sources.list.d/pgdg.list \
    && sudo apt update && sudo apt -y install libgl1 postgresql-client-16

