import os
def get_all_files(paths_list):
    files = []
    for path in paths_list:
        if os.path.isfile(path) and path not in files:
            files.append(path)
        elif os.path.isdir(path):
            for f in os.listdir(path):
                fp = os.path.join(path, f)
                if os.path.isfile(fp) and fp not in files:
                    files.append(fp)
    return files