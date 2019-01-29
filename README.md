# rcghci - A remote control for GHCI

This is a python3 script that straps on something like a RPC interface to a GHCI process.

You can install it using `pip`

```
pip3 install rcghci
```

To start it, open a terminal and set the following environment variables.

```
export RCGHCI_ERROR_FILE=/home/<username>/errors.txt
export RCGHCI_PROMPT='RCGHCIPROMPT>>>'
```

Now change directory to your project, and instead of running `stack ghci`
run `rcghci` followed by what ever options that you have to pass to the `stack ghci` command.

You will see the `stack ghci` command starting up, and if you have the `tkinter` library installed
a gui will open up.

You can install the tkinter library using the following command

```
sudo apt-get install python3-tk
```

### Configuring neovim

Add the following lines to you neovim configuration.

```
let g:rcghci_ip = "127.0.0.1"
let g:rcghci_port = "1880"
let g:error_path = "~"

function! Ghci(command)
  silent exec "!echo ". a:command . "> /dev/tcp/" . g:rcghci_ip . "/" . g:rcghci_port
endfunction

function! GHCIBridgeSetErrors()
  hi StatusLine ctermfg=black guibg=black ctermbg=red guifg=#fc4242
endfunction

function! GHCIBridgeSetWarnings()
  hi StatusLine ctermfg=black guibg=black ctermbg=yellow guifg=#84ff56
endfunction

function! GHCIBridgeSetSuccess()
  hi StatusLine ctermfg=black guibg=black ctermbg=green guifg=#087e3b
endfunction

function! GHCIBridgeSetActivity()
  hi StatusLine ctermfg=black guibg=black ctermbg=brown guifg=orange
endfunction

function! LiveCompile()
  call Ghci(":reload")
endfunction

function! OpenErrors()
  execute ":cclose"
  execute ":cfile " . g:error_path ."/errors.txt"
  execute ":cope"
endfunction

function! CloseErrors()
  cclose
endfunction

command! HSendConfig call Ghci("socket=".$NVIM_LISTEN_ADDRESS)

autocmd BufWritePost *.hs call LiveCompile()
```

After you start the nvim editor, just call the `HSendConfig` command, which sends the neovim rpc socket
to the RCGHCI script.

open a Haskell source file in your project (The same one you have started the rcghci script in) to start using the script.

# Live Reload

The neovim configuration we have added will send a reload command to the script when a Haskell file is saved. This causes
the wrapped rcghci script to do a ":reload" command, and ends up reloading all the changed files. The output of the ghci
process is parsed by the script into errors and warnings. These are then written to an error file, who's path we have configured
using the `RCGHCI_ERROR_FILE` environment variable. We have also set the path of the vim error file to be the same. This means
you can use vim's native error file navigation capabilities to navigate the error locations, including the ability to open them
in the editor simply by pressing `enter` when the cursor is on the path in the vim's error list display.

When you have triggerred a reload by saving a Haskell source file, the script will change the color of the status bar to indicate
that a command is in progress. It will switch the status bar color after the command has finished execution. If there are any errors
it will be a different color. You can configure the colors by changing them in the `GHCIBridgeSetErrors()`, `GHCIBridgeSetWarnings()`
functions.

# Using the GUI

You can also open an error location in neovim by clicking on the error that is displayed in the gui.
