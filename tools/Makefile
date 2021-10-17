CFLAGS  = -O3 -g -Wall -I../Demo/trace
LDFLAGS =

SRC     = gentrace.c
OBJECTS = $(SRC:.c=.o)
EXE     = gentrace

.SUFFIXS: .c .o

.PHONY: clean

%.o: %.c
	$(CC) -c -o $@ $< $(CFLAGS)

$(EXE): $(OBJECTS)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $(EXE) $(OBJECTS)

clean:
	-$(RM) $(OBJECTS) $(EXE)

distclean: clean

