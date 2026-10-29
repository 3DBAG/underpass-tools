# Native dependencies stay in their pinned Nix closure, independently of Python.
FROM nixos/nix:2.24.11 AS native
ENV NIX_CONFIG="experimental-features = nix-command flakes"
COPY native /src/native
WORKDIR /src/native/carving
RUN nix build --out-link /native-result . && \
    mkdir /closure && cp -a $(nix-store --query --requisites /native-result) /closure/
WORKDIR /src/native/zigpip
RUN nix develop /src/native/carving --command zig build -Doptimize=ReleaseFast --prefix /zigpip

FROM python:3.12-slim AS runtime
COPY --from=native /closure/ /nix/store/
COPY --from=native /native-result/bin/add_underpass /usr/local/bin/add_underpass_native
COPY --from=native /zigpip/lib/libzigpip.so /opt/underpass-tools/lib/libzigpip.so
ENV UNDERPASS_ZIGPIP_PREBUILT=/opt/underpass-tools/lib/libzigpip.so
ENV EXE_PATH_ADD_UNDERPASS_NATIVE=/usr/local/bin/add_underpass_native
COPY . /src/underpass-tools
RUN pip install --no-cache-dir /src/underpass-tools
ENTRYPOINT ["add-underpasses"]
