from .rcrepl import ReplServer, log
import tempfile
import os
import sys

def make_error_blocks(content):
    errors = []
    warnings = []
    if content is not None and len(content) > 0:
        if "\n\n" in content:
            blocks = content.split("\n\n")
        else:
            blocks = content.split("\r\n")
        for b in blocks:
            lines = b.strip().split("\n")
            for idx, line in enumerate(lines):
                try:
                    (file_name, line, column, type_, msg) = line.split(":")[0:5]
                except Exception as err :
                    continue
                type_ = type_.strip()
                err_msg = "\n".join(lines[idx:])
                full_item =  {'file_name': file_name, 'line': line, 'column' : column, 'text': err_msg }
                if "error" in type_:
                    errors.append(full_item)
                elif "warning" in type_:
                    warnings.append(full_item)
    return {"errors" : errors, "warnings": warnings}

def remove_init_file():
    os.remove(tempfile.gettempdir() + "/rcghci")

def main():
    try:
        try:
            COMMAND_PORT = int(os.environ['RCGHCI_PORT'])
        except:
            COMMAND_PORT = 1880

        with open(tempfile.gettempdir() + "/rcghci", "w") as f:
            f.write(str(COMMAND_PORT))
        try:
            PROMPT = os.environ['RCGHCI_PROMPT']
            if len(PROMPT) < 5:
                raise Exception("ERROR ! Empty or short prompt found. Please use a prompt with more than five characters. You can configure the GHCI prompt by adding the line ':set prompt <prompt>' to ~/.ghci file. Then configure rcghci to use that prompt by setting the RCGHCI_PROMPT env variable using 'export RCGHCI_PROMPT=<prompt>' command from termial, before starting RCGHCI. This is so that RCGHCI script can detect when a command has finished execution.")
        except KeyError:
                raise Exception("ERROR ! The environment variable `RCGHCI_PROMPT` which is supposed to hold the custom ghci prompt was not found. You can set a custom GHCI prompt by adding the line ':set prompt <prompt>' to ~/.ghci file. Then configure rcghci to use that prompt by setting the RCGHCI_PROMPT env variable using 'export RCGHCI_PROMPT=<prompt>' command from termial, before starting RCGHCI. This is so that RCGHCI script can detect when a command has finished execution.")
        log("Using prompt : {}".format(PROMPT))
        master_server = ReplServer(PROMPT, "stack", ["ghci"] + sys.argv[1:], ('0.0.0.0', COMMAND_PORT), make_error_blocks)
        master_server.start()
    except KeyboardInterrupt:
        remove_init_file()
