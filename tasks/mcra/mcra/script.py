import os
import subprocess
from pathlib import Path
from shutil import which


def run_mcra(input_dir, output_dir, mcra_path=None, dotnet_bin="dotnet", extra_args=None):
    mcra_path = mcra_path or os.environ.get("MCRA_PATH", "mcra")
    mcra_path_str = str(mcra_path)
    input_dir_path = Path(input_dir).resolve() if input_dir else None
    output_dir_path = Path(output_dir).resolve()

    if mcra_path_str.endswith(".dll"):
        if not which(dotnet_bin):
            raise FileNotFoundError(f"{dotnet_bin} not found in PATH")
        command = [dotnet_bin, mcra_path_str, "run"]
    else:
        if not which(mcra_path_str):
            raise FileNotFoundError(f"MCRA executable not found: {mcra_path_str}")
        command = [mcra_path_str, "run"]

    command += [
        "-o",
        str(output_dir_path),
    ]
    if extra_args:
        command.extend(list(extra_args))
    if input_dir_path:
        command.append(str(input_dir_path))

    result = subprocess.run(command, capture_output=True, text=True)

    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)

    result.check_returncode()
