FROM mcr.microsoft.com/devcontainers/python:3.13-bookworm

ENV PYTHONUNBUFFERED=1

COPY "./.devcontainer/build-gst-126-from-source.sh" "/build-gst-126-from-source.sh" 

RUN apt-get update && apt-get remove -y python3 && apt-get install -y ffmpeg libsm6 libxext6 vulkan-tools cmake ninja-build gcc libturbojpeg0 flex bison

RUN bash /build-gst-126-from-source.sh

RUN usermod -a -G dialout vscode

USER vscode

ENV PATH="$PATH:/home/vscode/.local/bin"

COPY Backend/requirements.txt /tmp/pip-tmp/
RUN --mount=type=cache,target=/root/.cache/pip pip3 --disable-pip-version-check install -r /tmp/pip-tmp/requirements.txt \
   && sudo rm -rf /tmp/pip-tmp

COPY CDCServer/requirements.txt /tmp/pip-tmp/
RUN --mount=type=cache,target=/root/.cache/pip pip3 --disable-pip-version-check install -r /tmp/pip-tmp/requirements.txt \
   && pip3 --disable-pip-version-check install 'uvicorn[standard]' && sudo rm -rf /tmp/pip-tmp

RUN export DEBIAN_FRONTEND=noninteractive && wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add - \
    && echo "deb http://apt.postgresql.org/pub/repos/apt/ `lsb_release -cs`-pgdg main" | sudo tee /etc/apt/sources.list.d/pgdg.list \
    && sudo apt update && sudo apt -y install libgl1 postgresql-client-16

CMD ["sleep", "infinity"]