# Changelog

## [0.3.0](https://github.com/menil/pulumi-reolink/compare/pulumi-reolink-v0.2.1...pulumi-reolink-v0.3.0) (2026-09-01)


### Features

* support zoom, focus, AI vehicle, and doorbell settings ([ec51b49](https://github.com/menil/pulumi-reolink/commit/ec51b49ee262da794045f25135894c0fcbaafeaa))


### Bug Fixes

* correct uv.lock jsonpath filter, resync lockfile ([93a20f9](https://github.com/menil/pulumi-reolink/commit/93a20f9e519d75926a54705b57613600592d7846))

## [0.2.1](https://github.com/menil/pulumi-reolink/compare/pulumi-reolink-v0.2.0...pulumi-reolink-v0.2.1) (2026-09-01)


### Bug Fixes

* sync uv.lock on release, publish within the same workflow run ([40fe78b](https://github.com/menil/pulumi-reolink/commit/40fe78b95c3b0b4f5d462f9dd5224e309777571e))

## [0.2.0](https://github.com/menil/pulumi-reolink/compare/pulumi-reolink-v0.1.0...pulumi-reolink-v0.2.0) (2026-09-01)


### Features

* add pyproject.toml packaging config for PyPI ([1fad1ce](https://github.com/menil/pulumi-reolink/commit/1fad1ce497495024517786d86aff41d49e22dbdd))
* add python and uv to nix dev shell ([69df0a6](https://github.com/menil/pulumi-reolink/commit/69df0a6cc118f7f2028c0f7f23669c593d6263f5))
* add settings translation layer with reflection fallback ([f5b3b6b](https://github.com/menil/pulumi-reolink/commit/f5b3b6b8dc5ab0130d10fc8366338d947146c10e))
* adopt newly bootstrapped cameras via pulumi import_ ([8a16b14](https://github.com/menil/pulumi-reolink/commit/8a16b149778853ed6a799b7b9f5b5eda799c01b2))
* commits to bump minor normally. ([7da01a0](https://github.com/menil/pulumi-reolink/commit/7da01a019699ad263e69eb78fd1f529ac0b1f57f))
* fetch camera name from device, auto-derive secret key ([467de04](https://github.com/menil/pulumi-reolink/commit/467de04806f5f3d00117eb230362260e871e57e1))
* implement bootstrap.py CLI for importing cameras ([ef8872a](https://github.com/menil/pulumi-reolink/commit/ef8872a517b9c0a7732b3a3da7a6d1d2b88057c4))
* implement example Pulumi program ([e688c86](https://github.com/menil/pulumi-reolink/commit/e688c8698036dc4d55d3de49f8436593cc102927))
* implement ReolinkDevice Pulumi dynamic resource ([79276ca](https://github.com/menil/pulumi-reolink/commit/79276ca29c4d55d30463265a29b275ffef9101d1))
* mask password input, add progress/error UX, cap connect time ([8e973dc](https://github.com/menil/pulumi-reolink/commit/8e973dc75366105ed5f834ff5dc38b214525d585))
* scaffold pulumi_reolink package and example project layout ([84a0f4c](https://github.com/menil/pulumi-reolink/commit/84a0f4c68406184f06f475bc51269044fbff5926))
* support 8 more camera settings ([312b6e8](https://github.com/menil/pulumi-reolink/commit/312b6e872afb68a2a41116c5e96f02f29d8e7721))
* wire Justfile recipes to ruff, mypy, and pytest ([f4cf4a0](https://github.com/menil/pulumi-reolink/commit/f4cf4a09dcf1742d13a1e01dd7f5a2b869fa0d10))


### Bug Fixes

* gate settings on camera capability, revert broken import_ ([fd7d4a4](https://github.com/menil/pulumi-reolink/commit/fd7d4a4ec3612dc84bc278aea59690f295501320))
* int settings arrive at apply_setting() as floats ([7b5507e](https://github.com/menil/pulumi-reolink/commit/7b5507e1db40e46c7639196349d7ce17e026d959))
* pulumi preview couldn't find the python language plugin ([bd030c2](https://github.com/menil/pulumi-reolink/commit/bd030c26f8c06515bff1860f5ae8d93c71d0b52f))
* pulumi preview couldn't load the ReolinkDevice provider ([ebe03c4](https://github.com/menil/pulumi-reolink/commit/ebe03c4caa47eb74e930dc9108e1cb35fe0ea48c))
* python -m pulumi_reolink.bootstrap did nothing ([21dd87e](https://github.com/menil/pulumi-reolink/commit/21dd87e8cdd30cab2bd9f5dddf7c4664a004a7c2))
* query push/recording/ftp/email/buzzer device-wide, add 7 settings ([acb93c7](https://github.com/menil/pulumi-reolink/commit/acb93c7b318bf64e2d239028acb39f0944056ae9))
* remove bump-patch-for-minor-pre-major from release-please config ([7da01a0](https://github.com/menil/pulumi-reolink/commit/7da01a019699ad263e69eb78fd1f529ac0b1f57f))
* reuse the repo's nix/uv venv instead of a second one ([07c4174](https://github.com/menil/pulumi-reolink/commit/07c4174805bc4e9c6d0501cb6159cb42f73b2152))
* sentinel getter values written back as real setting values ([3d2915b](https://github.com/menil/pulumi-reolink/commit/3d2915b7068196c30bea5b9e8a1e437cd56f5048))
* settings always read/applied as false/0 ([d622646](https://github.com/menil/pulumi-reolink/commit/d622646dbe5b11b35c443fe297e431e68deea86c))


### Documentation

* add MIT LICENSE file ([65ce2a1](https://github.com/menil/pulumi-reolink/commit/65ce2a15af0ba608750a55a9b38393da09949f6b))
* add pulumi-reolink technical specification ([307fa6e](https://github.com/menil/pulumi-reolink/commit/307fa6e6c5557b0c00a45e284c513b7a42f02809))
* add pulumi-reolink technical specification ([859ed3a](https://github.com/menil/pulumi-reolink/commit/859ed3abf3ce6c17a904c90eaaba99410030aaeb))
* add status badges and document settings-removal semantics ([4b8fcb5](https://github.com/menil/pulumi-reolink/commit/4b8fcb546c92e79ee75d38e70131f95dea993c42))
* reframe README as IaC and add a FAQ section ([f8b498a](https://github.com/menil/pulumi-reolink/commit/f8b498a7ea5baaf53aeb64a21b1dfbb691633c3f))
* rewrite README for pulumi-reolink usage ([6eb24c8](https://github.com/menil/pulumi-reolink/commit/6eb24c830817fd1fca51ad0f3599c58d359d1c92))
