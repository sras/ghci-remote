# rcghci - A remote control for GHCI

This is a python3 script that wraps a "stack ghci" command. 

1. It acts as a proxy that relays commands recieved on a tcp socket to the GHCI process.
2. If the required libs are available (TKInter gui library), it opens a GUI where the output from the ghci process and some configuration options are displayed.
3. It parses the output from GHCI process, seperate errors and warnings and displays them on the gui.
4. It also writes the output, to a text file. Editors can use this file to navigate through error locations in the source.
5. Right now, it can also control the Neovim editor via its RPC api, and do things like change the color of its status bar to indicate progress, error and success.

# Installing

rcghci can be installed by using pip3.

```
pip3 install rcghci
````

The Tkinter library for gui might need separate installation. If you are on Ubuntu or similar distributions you probably only have to do the `sudo apt-get install python3-tk`. The script will work even if you don't have this library. Just that the gui will not show up. Instead you will be able to 

1. See the ghci output in the terminal.
2. Get error output in a file, whoes location can be configured by the environment variable `GR_ERROR_FILE`.
3. Make use of Neovim editor integrations.

# Configuring the Neovim editor

Add the following vim script to be included in your neovim configuration.

```
let g:rcghci_ip = "127.0.0.1"
let g:rcghci_port = "1880"

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

command! HLiveCompile call SetLiveCompile(1)
command! HNoLiveCompile call SetLiveCompile(0)
command! HSendConfig call Ghci("socket=".$NVIM_LISTEN_ADDRESS)

autocmd BufWritePost *.hs call LiveCompile()

function! SetLiveCompile(lc)
  let g:live_compile = a:lc
endfunction

function! LiveCompile()
  if exists("g:live_compile") && g:live_compile == 1
    call Ghci(":reload")
  endif
endfunction

```



