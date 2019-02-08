from .rcrepl import WatchServer, log
import tempfile
import os
import sys

def make_error_blocks(content):
    try:
        print(content)
        #errors = json.loads(out)
        #for error in errors['errors']:
        #    for problem in error['problems']:
        #        filename = os.path.abspath(error['path'])
        #        line = problem['region']['start']['line']
        #        line_end = problem['region']['end']['line']
        #        col = problem['region']['start']['column']
        #        tag = problem['title']
        #        details =  ''.join([get_msg(x).strip() + '\n' for x in problem['message'] ])
        #        overview = ""
        #        items.append("{}:{}:{}\n    {}: {}\n    {}\n\n{}".format(filename, line, col, tag, overview, details.replace('\n', '\n    '), fm.get_region(filename, line, line_end)))
        return {"errors" : [], "warnings": []}
    except json.JSONDecodeError as e:
        print("Decoding failed" + str(e))
        pass

def remove_init_file():
    os.remove(tempfile.gettempdir() + "/rcelm")

def main():
    try:
        try:
            COMMAND_PORT = int(os.environ['RCGHCI_PORT'])
        except:
            COMMAND_PORT = 1880

        with open(tempfile.gettempdir() + "/rcelm", "w") as f:
            f.write(str(COMMAND_PORT))
        print(sys.argv)
        master_server = WatchServer(['elm', 'make', '--report', 'json', *(sys.argv[1:])], ('0.0.0.0', COMMAND_PORT), make_error_blocks)
        master_server.start()
    except KeyboardInterrupt:
        remove_init_file()
