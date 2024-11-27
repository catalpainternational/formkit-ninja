# Building Production Ready Images

```sh
josh@carbonmint:~/github/catalpainternational/formkit-ninja/.devcontainer$ docker build \
    -t registry.digitalocean.com/catalpa-container-registry/formkit-ninja \
    -f ./Dockerfile ..
```

(Add `--push` to push at the same time)

```
[+] Building 2.2s (13/13) FINISHED                                                                                       docker:default
 => [internal] load build definition from Dockerfile                                                                               0.0s
 => => transferring dockerfile: 1.83kB                                                                                             0.0s
 => [internal] load metadata for ghcr.io/astral-sh/uv:0.5                                                                          1.3s
 => [internal] load metadata for docker.io/library/python:3.13-slim                                                                2.1s
 => [internal] load .dockerignore                                                                                                  0.0s
 => => transferring context: 2B                                                                                                    0.0s
 => [builder 1/3] FROM docker.io/library/python:3.13-slim@sha256:4efa69bf17cfbd83a9942e60e2642335c3b397448e00410063a0421f9727c4c4  0.0s
 => FROM ghcr.io/astral-sh/uv:0.5@sha256:5436c72d52c9c0d011010ce68f4c399702b3b0764adcf282fe0e546f20ebaef6                          0.0s
 => [internal] load build context                                                                                                  0.0s
 => => transferring context: 64B                                                                                                   0.0s
 => CACHED [builder 2/3] RUN --mount=type=cache,sharing=locked,target=/var/cache/apt     apt-get update && export DEBIAN_FRONTEND  0.0s
 => CACHED [builder 3/3] COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv                                                0.0s
 => CACHED [sync 1/3] WORKDIR /app                                                                                                 0.0s
 => CACHED [sync 2/3] COPY pyproject.toml uv.lock /app/                                                                            0.0s
 => CACHED [sync 3/3] RUN --mount=type=cache,sharing=locked,target=/root/.cache/     uv sync ${NO_DEV_OPTION} --no-install-worksp  0.0s
 => exporting to image                                                                                                             0.0s
 => => exporting layers                                                                                                            0.0s
 => => writing image sha256:8a465245851335545340249bceb3966495f9c4764b59b1dbfab9778a72438df7                                       0.0s
 => => naming to registry.digitalocean.com/catalpa-container-registry/formkit-ninja    
```

# Building Dev Images

The 'dev' image is created using build args and a target, see the `docker.compose` file