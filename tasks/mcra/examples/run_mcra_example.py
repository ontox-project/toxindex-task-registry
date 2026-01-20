# 1) make sure to download MCRA from RIVM git
#       https://github.com/rivm-syso/mcra-core/releases

# 2) install donet
#       brew install --cask dotnet-sdk
#       dotnet --version

# 3) Install correct version of dotnet
#       ASP.NET Core 9.0
#       https://aka.ms/dotnet-core-applaunch?framework=Microsoft.AspNetCore.App&framework_version=9.0.0&arch=arm64&rid=osx-arm64&os=osx.26

#       microsoft.netcore.app 9.0.12
#       https://dotnet.microsoft.com/en-us/download/dotnet/9.0

# 4) create RIVM login to get example data (action folder.zip)
#       https://mcra.rivm.nl/mcra/#/



import sys
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1]))

from mcra.script import run_mcra  # noqa: E402


mcra_dll = Path.home() / "Downloads" / "MCRA.CLI" / "mcra.dll"
repo_root = Path(__file__).resolve().parents[3]
input_dir = (repo_root / "tasks/mcra/examples/task_input").resolve()
output_dir = (repo_root / "tasks/mcra/examples/mcra_output").resolve()

run_mcra(
    str(input_dir),
    str(output_dir),
    mcra_path=str(mcra_dll) if mcra_dll.exists() else None,
)
