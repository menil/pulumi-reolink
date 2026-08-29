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

  shellHook = ''
    echo "❄️ Welcome to the pulumi-reolink shell!"
    uv sync
    source .venv/bin/activate
  '';
}
