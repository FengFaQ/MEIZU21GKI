VERSION = 6
PATCHLEVEL = 1

headers_install:
	@mkdir -p $(O)/usr/include
	@rsync -mrq $(shell pwd)/* $(O)/usr/include

all:
	@true