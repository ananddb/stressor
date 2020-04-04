# Release stressor
# > Set-ExecutionPolicy -ExecutionPolicy unrestricted -Scope Process
# > cd C:\Prj\git\stressor
# > .\tools\release_stressor.ps1

Write-Error "Use `tox -e make_relase_msi` instead."
Exit 1

$ProjectRoot = "C:\Prj\git\stressor";

$BuildEnvRoot = "C:\prj\env\stressor_build_3.8";

$BuildFolder = "$ProjectRoot\build";


$IGNORE_UNSTAGED_CHANGES = 0;
$IGNORE_NON_MASTER_BRANCH = 0;
$SKIP_TESTS = 0;
$REUSE_BUILD_CACHE = 0;

# ----------------------------------------------------------------------------
# Pre-checks

$CUR_BRANCH = git rev-parse --abbrev-ref HEAD
if ($CUR_BRANCH -ne "master") {
    if( $IGNORE_NON_MASTER_BRANCH ) {
        Write-Warning "RELEASING NON-MASTER BRANCH: $CUR_BRANCH"
    } else {
        Write-Error "Not on master branch: $CUR_BRANCH!"
        Exit 1
    }
}

# Working directory must be clean
Set-Location $ProjectRoot
git status
git diff --exit-code --quiet
if($LastExitCode -ne 0) {
   if( $IGNORE_UNSTAGED_CHANGES ) {
       Write-Warning "IGNORING UNSTAGED CHANGES!"
   } else {
       Write-Error "Unstaged changes: exiting."
       Exit 1
   }
}


# ----------------------------------------------------------------------------
# Create and activate a fresh build environment

Set-Location $ProjectRoot

"Removing venv folder $BuildEnvRoot..."
Remove-Item $BuildEnvRoot -Force -Recurse -ErrorAction SilentlyContinue

"Creating venv folder $BuildEnvRoot..."
py -3.8 -m venv "$BuildEnvRoot"
# py -3.7 -m venv "$BuildEnvRoot"

Invoke-Expression "& ""$BuildEnvRoot\Scripts\Activate.ps1"""

# TODO: Check for 3.7
python --version

python -m pip install --upgrade pip

# Black is beta and needs --pre flag
#python -m pip install --pre black

#python -m pip install -r requirements-dev.txt
#python -m pip list

python -m pip install cx_Freeze
pipenv install --dev

python -m pip list

# Run tests
if( $SKIP_TESTS ) {
    Write-Warning "SKIPPING TESTS!"
} else {
    tox
    # python setup.py test
    if($LastExitCode -ne 0) {
        Write-Error "Tests failed with exit code $LastExitCode"
        Exit 1
    }
}


# --- Clear old build cache.
# (not neccessarily required, but may prevent confusion, like jinja2 vs. Jinja2)
if( $REUSE_BUILD_CACHE ) {
    Write-Warning "Re-using build cache: Strange things may happen: $BuildFolder..."
} else {
    "Removing build cache folder $BuildFolder..."
    Remove-Item $BuildFolder -Force -Recurse -ErrorAction SilentlyContinue
}

#--- Create MSI installer
#    This call causes setup.py to import and use cx_Freeze:
python setup.py bdist_msi
if($LastExitCode -ne 0) {
   Write-Error "Create MSI failed with exit code $LastExitCode"
   Exit 1
}

#--- Create source distribution and Wheel
#    This call causes setup.py to NOT import and use cx_Freeze:

python -m setup egg_info --tag-build="" -D sdist bdist_wheel --universal

if($LastExitCode -ne 0) {
   Write-Error "Create Wheel and/or upload failed with exit code $LastExitCode"
   Exit 1
}

#--- Done.

"SUCCESS."
"We should now:"
"  1. twine upload dist\stressor-x.y.z.tar.gz"
"  2. twine upload dist\stressor-x.y.z-py2.py3-none-any.whl"
"  3. Release on GitHub"
"  4. Upload dist\stressor-x.y.z-win32.msi on GitHub"
"  5. Update changelog"
"  6. Bump version and commit/push"
