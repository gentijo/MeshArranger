echo "Sync Device"

# ${workspaceFolder}: the path of the workspace folder of the saved file
# ${file}: path of saved file
# ${fileBasename}: saved file's basename
# ${fileDirname}: directory name of saved file
# ${fileExtname}: extension (including .) of saved file
# ${fileBasenameNoExt}: saved file's basename without extension
# ${relativeFile} - the current opened file relative to ${workspaceFolder}
# ${cwd}: current working directory (this is the working directory that vscode is running in not the project directory)

export filedir=$1
export workspaceFolder=$2
export filename=$3
export basename=$4
echo $0
echo $filedir
echo $workspaceFolder
echo $filename
echo $basename 


cd $filedir
rm $basename.mpy
# echo "Compiling" && python -m mpy_cross $filename
mpremote a0 mkdir :/dnet-gtwy
mpremote a0 cp $basename.py :/dnet-gtwy/$basename.py
mpremote a0 cp $basename.mpy :/dnet-gtwy/$basename.mpy

