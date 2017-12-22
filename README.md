# ghci-remote

This is a simple python3 script that wraps a "stack ghci" command, capture its input/output and display it in a Python gui.
The python script opens 3 network sockets. You can send text commands to one of these socket and the script will relay 
it to the wrapped REPL and display its output. The output is parsed and if there are errors/warnings they will be formatted and 
displayed in a separate pane.

# Installing

This script uses Tkinter library to draw the GUI. So you have to install it for Python3. If you are on Linux you 
probaby can just do something like to install it.

```
sudo apt-get install python3-tk
```

There are two optional dependencies. https://pypi.python.org/pypi/psutil and the neovim module. If you have psutils, the 
script will show the memory usage of all running ghc instances. If you install neovim module, you will be able to click on the error
messages displayed in the gui, and have the file opened and cursor placed on the error in a running neovim instance. 

# How to use?

Clone this repo somewhere on your system. Then go to the directory of your haskell stack project. Instead of running `stack ghci`
run 'python3 /path/to/bridge.py'. It will start the gui and you can see the output from the ghci instance in the terminal and in the
gui. After ghci has been loaded (you will see something like "Loaded Ghci configuration blah blah" in the gui.
At this point you can change a haskell file in your project. And after that, open a terminal and enter the following command

```
echo ":reload"> /dev/tcp/127.0.0.1/1880
```

This will send the string ":reload" to the 1880 port (where the script listens for commands by default). You should be able to see
the ghci reloading the changed file, and the errors/warning getting displayed in the gui.

I have these lines in my init.vim neovim configuration file, that sends 
the aforementioned command upon file save (after checking a flag).

```
let g:compile_ip = "127.0.0.1"
let g:compile_port = "1880"

autocmd BufWritePost *.hs call LiveCompile()

function! Ghci_command(command)
  silent exec "!echo ". a:command "> /dev/tcp/" . g:compile_ip . "/" . g:compile_port 
endfunction

function! LiveCompile()
  if g:live_compile == 1
    call Ghci_command(":reload")
  endif
endfunction
```

Also, there is a small text input box at the bottom right of the gui. If you enter a file path there, like /tmp/errors.txt, the 
script will write the errors captured from the output into that file. And you can use your editors native mechanism to navigate
the error list files to jump throught the errors.


