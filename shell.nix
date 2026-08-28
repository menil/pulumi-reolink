{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    git
    gh
    just
    python311
    uv
    pulumi
  ];

  shellHook = ''
    echo "❄️ Welcome to the pulumi-reolink shell!"
    uv sync
    source .venv/bin/activate
  '';
}
