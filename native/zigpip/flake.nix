{
  description = "Fast Zig point-in-polygon library with Python bindings";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      lib = nixpkgs.lib;
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = f: lib.genAttrs systems (system: f system);
    in
    {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          zigVersion = "0.17.1";
          zigTargets = {
            x86_64-linux = {
              target = "x86_64-linux";
              sha256 = "3581863e3cbcfd0fce0efc682ce7e9e93da96668a977791d356a26d2a7e9b17a";
            };
            aarch64-linux = {
              target = "aarch64-linux";
              sha256 = "a1546d5646eb184437918d6635ca6b762a0e889eac09cef720ee7a1ed3fe7795";
            };
            x86_64-darwin = {
              target = "x86_64-macos";
              sha256 = "9af07b20319fbd0c92ee46ad23e81d6a782b1aaea2cfb8dcbff35f1d2c7ddbb7";
            };
            aarch64-darwin = {
              target = "aarch64-macos";
              sha256 = "75f1bc7a1e9852f17ec9a0c1895f767c4ec56d46bc8a834920eece1d0359dd8d";
            };
          };
          zigTarget = zigTargets.${system};
          # Pin the official binary independently of the nixpkgs Zig version.
          zig = pkgs.stdenvNoCC.mkDerivation {
            pname = "zig";
            version = zigVersion;
            src = pkgs.fetchurl {
              url = "https://ziglang.org/download/${zigVersion}/zig-${zigTarget.target}-${zigVersion}.tar.xz";
              inherit (zigTarget) sha256;
            };
            dontConfigure = true;
            dontBuild = true;
            dontStrip = true;
            installPhase = ''
              runHook preInstall
              mkdir -p "$out/bin" "$out/lib"
              cp zig "$out/bin/zig"
              cp -r lib/. "$out/lib/"
              runHook postInstall
            '';
            meta.mainProgram = "zig";
          };
          python = pkgs.python312.withPackages (ps: with ps; [
            numpy
            matplotlib
            laspy
            lazrs
            shapely
            pyproj
          ]);
        in
        {
          default = pkgs.mkShell {
            packages = [
              zig
              pkgs.zls
              python
            ];

            shellHook = ''
              export PYTHONPATH="$PWD/python${PYTHONPATH:+:$PYTHONPATH}"
            '';
          };
        });
    };
}
