import os

def print_tree(startpath, indent=""):
    files = os.listdir(startpath)
    files.sort()
    for index, name in enumerate(files):
        path = os.path.join(startpath, name)
        is_last = index == len(files) - 1
        connector = "└── " if is_last else "├── "
        print(indent + connector + name)
        if os.path.isdir(path):
            extension = "    " if is_last else "│   "
            print_tree(path, indent + extension)

if __name__ == "__main__":
    project_path = "."  # change to your project folder path
    print(os.path.basename(os.path.abspath(project_path)))
    print_tree(project_path)
