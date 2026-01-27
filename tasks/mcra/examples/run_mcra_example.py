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

# 4) Make action template on windows machine
#       Download MCRA.CLI.10.2.12.zip file on windows machine and locate in Downloads
#       In Downloads folder unzip
#       cd on the terminal to Downloads/MCRA.CLI.10.2.12/MCRA.CLI 
#       find mcra.exe there and run command
#       >mcra.exe create test_mcra_action_template -a SingleValueRisk
#       a new empty template folder with the name specified above is created in the MCRA.CLI folder

# 5) invoke on the command line for testing
#       % dotnet ~/Downloads/MCRA.CLI/mcra.dll run -o /Users/michael/Git/ONTOX/toxindex-task-registry/tasks/mcra/examples/mcra_output /Users/michael/Git/ONTOX/toxindex-task-registry/tasks/mcra/examples/task_input/test_mcra_action_template

# *) create RIVM login to get example data (action folder.zip)
#       https://mcra.rivm.nl/mcra/#/

import sys
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1]))

from mcra.script import run_mcra  # noqa: E402


mcra_dll = Path.home() / "Downloads" / "MCLI.CLI" / "mcra.dll"
repo_root = Path(__file__).resolve().parents[3]
input_dir = (repo_root / "tasks/mcra/examples/task_input/test_mcra_action_template").resolve()
output_dir = (repo_root / "tasks/mcra/examples/mcra_output").resolve()

run_mcra(
    str(input_dir),
    str(output_dir),
    mcra_path=str(mcra_dll) if mcra_dll.exists() else None,
)
