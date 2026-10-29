# 环境、验证与跨机器运行

只写论文或查看结果：运行 `python3 scripts/check_handoff.py`，无需安装实验依赖。

实验参考环境：macOS arm64、Python 3.13.13、imagecodecs 2026.10.10、libjxl 0.12.0、libjpeg-turbo 3.1.4.1；Python 包精确版本见 `requirements.lock.txt`。当前 imagecodecs 版本要求 Python ≥3.12，建议沿用 Python 3.13。

## macOS

```bash
brew install python@3.13 jpeg-turbo
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python scripts/build_coefficients.py
python -m pytest -q -W error
```

构建脚本通过 `brew --prefix jpeg-turbo` 查找依赖，不再写死 `/opt/homebrew`，编译器默认 `cc`。支持 `--jpeg-prefix` 和 `--compiler`，或环境变量 `WSI_JPEG_PREFIX`、`CC`。

## Linux / Windows WSL

Linux 构建路径已加入，输出 `.so`；**本次没有 Linux 实机执行结果，不宣称已经跨平台验证**。原生 Windows 不在适配器支持范围，使用 WSL。

在已有 Python 3.13 的 Debian/Ubuntu 环境安装 C 编译器与 libjpeg 开发头文件，例如：

```bash
sudo apt-get install build-essential libjpeg-dev
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python scripts/build_coefficients.py
python -m pytest -q -W error
```

系统 JPEG 库版本可能与参考环境不同，应记录版本并通过完整往返测试；编码结果大小和运行时间不承诺跨版本完全相同。`native.py` 的原生 libjxl 接口会明确拒绝未经本项目验证的 libjxl 版本。

## 获取数据与最小运行

公开下载入口、大小和 SHA-256 见 [data/README.md](../data/README.md)。原切片不进入 Git。`tests/fixtures/` 已包含一个有出处的小型 RGB JPEG 回归图块，常规测试不需要整份 WSI。

从仓库根目录运行，输出文件必须不存在：

```bash
mkdir -p runs
PYTHONPATH=src python scripts/archive_cli.py encode \
  data/CMU-1-Small-Region.svs runs/smoke.wjxl \
  --group-tiles 16 --report runs/smoke-encode.json
PYTHONPATH=src python scripts/archive_cli.py decode \
  runs/smoke.wjxl --output runs/smoke-restored.svs \
  --report runs/smoke-decode.json
cmp data/CMU-1-Small-Region.svs runs/smoke-restored.svs
```

这是新机器的基础功能验证，不复现第五/六轮最小文件。对应研究实验需分别读 ROUND2–ROUND6；不要让新运行覆盖 `results/` 的历史证据。用新输出目录保存系统、依赖和源码版本。

## 二进制产物交接

本机的 `results/round3-packets/` 至 `round6-packets/` 共约 46.7 MB，完整 `.wjxl` 实验归档合计约 1.35 GB，未放入普通 Git。若要在另一台机器独立重验历史文件，可单独传输这些目录及其对应报告，按记录的 SHA-256 核验；不要传输 `.venv/` 或 `build/`，它们必须在目标机器重建。

传输系数包后可运行：

```bash
PYTHONPATH=src python scripts/verify_round4.py \
  results/round6-weak-entropy.json --output runs/round6-reverified.json
```

该命令还需要清单引用的第五轮原生对照包。仅有 Git 中的 JSON 报告不等于已获得二进制载荷。
