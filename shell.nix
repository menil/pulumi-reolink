{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    git
    gh
    just
    python311
    uv
    pulumi
    # nixpkgs splits Pulumi's language plugins into separate packages
    # instead of bundling them with `pulumi` like the official installer
    # does -- without this, `pulumi preview`/`up` fail with "no language
    # plugin 'pulumi-language-python' found".
    pulumiPackages.pulumi-python
  ];

  # uv installs prebuilt Linux wheels (grpcio, which Pulumi's Python SDK needs) that look for
  # the C++ runtime in the system library path, and a Nix shell does not see that path, so
  # importing them fails with "libstdc++.so.6: cannot open shared object file". Point the
  # loader at Nix's own copy. Only Linux needs it: macOS wheels do not use libstdc++ this way.
  LD_LIBRARY_PATH = pkgs.lib.optionalString pkgs.stdenv.isLinux (
    pkgs.lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib ]
  );

  shellHook = ''
    echo "❄️ Welcome to the pulumi-reolink shell!"
    uv sync
    source .venv/bin/activate
  '';
}
