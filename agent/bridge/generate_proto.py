"""生成 gRPC Python 代码

运行此脚本将 .proto 文件编译为 Python 代码。
"""

import subprocess
import sys
from pathlib import Path


def generate_proto():
    """生成 gRPC Python 代码"""
    proto_dir = Path(__file__).parent / "proto"
    proto_file = proto_dir / "matching_engine.proto"

    if not proto_file.exists():
        print(f"错误: 找不到 proto 文件: {proto_file}")
        sys.exit(1)

    # 编译 proto 文件
    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"--proto_path={proto_dir}",
        f"--python_out={proto_dir}",
        f"--grpc_python_out={proto_dir}",
        str(proto_file),
    ]

    print(f"运行: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"编译失败:\n{result.stderr}")
        sys.exit(1)

    print("编译成功!")
    print(f"生成文件:")
    for f in proto_dir.glob("*_pb2*.py"):
        print(f"  - {f.name}")


if __name__ == "__main__":
    generate_proto()
