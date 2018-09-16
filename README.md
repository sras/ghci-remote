# rcghci - A remote control for GHCI

This is a simple python3 script that wraps a "stack ghci" command. 

1. It acts as a proxy that relays commands recieved on a tcp socket to the GHCI process.
2. If the required libs are available (TKInter gui library), it opens a GUI where the output from the ghci process and some configuration options are displayed.
3. It parses the output from GHCI process, seperate errors and warnings, counts them and display the report on the gui.
4. It also writes the output, to a text file. Editors can use this file to navigate through error locations in the source.
5. It can also control the neovim editor via its RPC api, and do things like change the color of its status bar to indicate progress, error and success.

# Installing

This script uses Tkinter library to draw the GUI. So you have to install it for Python3. If you are on Linux you 
probaby can just do something like the following to install it.

```
sudo apt-get install python3-tk
```

The script will work even if you don't have this library. Just that the gui will not show up.

# How to use?

Clone this repo somewhere on your system. Then go to the directory of your haskell stack project. Instead of running `stack ghci`
run 'python3 /path/to/bridge.py'. It will start the gui and you can see the output from the ghci instance in the terminal and in the
gui. After ghci has been loaded (you will see something like "Loaded Ghci configuration blah blah" in the gui.
At this point you can edit a haskell file in the same project. And after that, open a terminal and enter the following command

```
echo ":reload"> /dev/tcp/127.0.0.1/1880
```

This will send the string ":reload" to the 1880 port (where the script listens for commands by default). You should be able to see the ghci reloading the changed file, and the errors/warning getting displayed in the gui. 

In your editor, you just need to configure to execute this shell command when a Haskell file is saved.

```
echo ":reload"> /dev/tcp/127.0.0.1/1880
```

So in my neovim config I have something like this.

```
function! LiveCompile()
  silent exec "!echo :reload> /dev/tcp/127.0.0.1/1880"
endfunction

autocmd BufWritePost *.hs call LiveCompile()  
```

# Navigating the errors/warnings

There are two ways to do this using this gui. 

1. If you are using neovim, you can click on the errors/warning displayed in the gui and the gui will make neovim open the file and place the curson at the error location. To make this work, you should have the python module, `neovim`, available. You can install it using pip. 

After this, start the gui and from neovim, execute the following command.

```
  silent exec "!echo socket=" . $NVIM_LISTEN_ADDRESS . "> /dev/tcp/127.0.0.1/1880"
```

This sends the path of the unix socket where neovim expects external commands, to the gui. Once this is done, you will be able
to click on the errors/warnings in the gui, and neovim will open the location.

2. There is a small text input box at the bottom right of the gui. If you enter a file path there, like /tmp/errors.txt, the 
script will write the errors captured from the output into that file. And you can use your editors native mechanism to navigate
the error list files to jump throught the errors.

# Get type of selected expression

There is some ceremony to get this working. It involves the following steps.

1. Enable the gathering of type info for the wrapped ghci instance using ":set +c" command.
2. Reload the current file using file path
3. Visually select an expression, and call the following vim function that send the current file name and selected range
   as arguments to the ':type-at' ghci command.
   
The type will be displayed in the output pane.
