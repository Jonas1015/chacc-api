<p style="font-size:3.2em" align="center">  ChaCC API </p>

<a href="https://chacc.dev" target="blank"><p align="center">
  <img src="chacc_api/assets/chacc-icon.ico" alt="ChaCC API" />
</p></a>



<p align="center"><b>Build modular APIs with independent, pluggable components.</b></p>

<p align="center">ChaCC API is a FastAPI-based platform that lets you build and plug in Python modules like apps. Each module is self-contained – routes, models, logic – and can be installed, updated, or removed without touching the core. </p>

<p align="center"> For the full story, visit <a href="https://chacc.dev" target="blank">chacc.dev</a>.</p>


## Why ChaCC?

- **Modular by design** – Add, remove, or update features without touching the core
- **Plug and play** – Install pre-built modules and get working APIs instantly. No code required
- **Auto database migrations** – Models define their own schema, migrations run automatically
- **Hot reload** – See changes instantly during development
- **Simple deployment** – Package modules as `.chacc` files and deploy anywhere

## Quick Start

```bash
pip install chacc-api
chacc run server --dev
```

Open [http://localhost:8085/docs](http://localhost:8085/docs) to see your API.

## Examples

Official modules maintained by the ChaCC team. All modules are actively being developed – testers welcome:

- [chacc_authentication](https://github.com/tnet-tech/chacc_authentication) – Auth module with JWT, registration, and login
- [chacc_file_manager](https://github.com/tnet-tech/chacc_file_manager) – File management with pluggable adapters. Built-in local storage; bring your own for S3, Google Drive, FTP, or any custom backend.

Build your own module: [Module Development Guide](https://chacc.dev/modules)

## Documentation

Full docs, guides, and API reference: [chacc.dev](https://chacc.dev)

## Contributing

We welcome contributions! Check out [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

## Join the Community
Connect with people that uses ChaCC API on GitHub discussions. [Click here](https://github.com/tnet-tech/chacc-api/discussions)

## Changelog

See what's new in each release: [chacc.dev/changelog](https://chacc.dev/changelog)

[![PyPI](https://img.shields.io/pypi/v/chacc-api?label=PyPI&color=blue)](https://pypi.org/project/chacc-api/)
[![Python](https://img.shields.io/pypi/pyversions/chacc-api?label=Python&color=blue)](https://pypi.org/project/chacc-api/)
[![License](https://img.shields.io/pypi/l/chacc-api?label=License&color=blue)](https://github.com/tnet-tech/chacc-api/blob/main/LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/tnet-tech/chacc-api/ci.yml?label=CI)](https://github.com/tnet-tech/chacc-api/actions/workflows/ci.yml)
[![Star on Github](https://img.shields.io/github/stars/tnet-tech/chacc-api.svg?style=flat-square)](https://github.com/tnet-tech/chacc-api)
[![Discussions](https://img.shields.io/badge/Join-Discussions-blue)](https://github.com/tnet-tech/chacc-api/discussions)

