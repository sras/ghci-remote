from setuptools import setup, find_packages

setup(
    name = "rcghci",
    description='A script that wraps a GHCI instance and make it available as a langauge server for editors.',
    url='http://github.com/sras/ghci-remote',
    author='Sandeep.C.R',
    author_email='sandeepcr2@gmail.com',
    license='MIT',
    version = "1.03",
    packages = ['rcghci'],
    entry_points = {
        "console_scripts":['rcghci=rcghci.rcghci:main']
    },
    install_requires=[
      'pexpect',
      'psutil',
      'neovim'
    ]
)
