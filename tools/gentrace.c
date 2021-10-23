// Copyright (c) 2021 Kuoping Hsu
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "btf_trace.h"

void usage(void) {
    printf("Usage: gentrace dump.bin trace.btf\n");
}

static char *get_taskname(
    TRACE *trace_data,
    int index
) {
    char *ptr = (char*)&trace_data->d.task_lists;
    int n = trace_data->h.max_task_name_len * index;
    return (char*)&ptr[n];
}

static EVENT *get_event(
    TRACE *trace_data,
    int index
) {
    char *ptr = (char*)&trace_data->d.task_lists;
    int n = trace_data->h.max_tasks * trace_data->h.max_task_name_len +
            sizeof(EVENT) * index;
    return (EVENT*)&ptr[n];
}

int gentrace(
    char *infile,
    char *outfile
) {
    TRACE *trace_data;
    FILE *fin, *fout;
    int i;
    int current_task;
    int current_index;
    int result;

    if ((fin = fopen(infile, "rb")) == NULL) {
        printf("file %s not found\n", infile);
        return 1;
    }
    if ((fout = fopen(outfile, "w")) == NULL) {
        printf("file %s can not be created\n", outfile);
        return 1;
    }

    // get file size
    fseek(fin, 0, SEEK_END);
    int size = ftell(fin);
    fseek(fin, 0, SEEK_SET);

    if ((trace_data = malloc(size)) == NULL) {
        printf("malloc error\n");
        return 1;
    }

    result = fread((void*)trace_data, sizeof(char), size, fin);
    if (result != size) {
        printf("data read error\n");
        return 1;
    }

    // Check header
    if (trace_data->h.header[0] != 'B' ||
        trace_data->h.header[1] != 'T' ||
        trace_data->h.header[2] != 'F' ||
        trace_data->h.header[3] != '2') {
        printf("The header of trace data is not correct.\n");
        return 1;
    }

    // TODO: check endian. If this value is not 1, the rest values
    // should be converted to another endian. (big endian <-> little endian)
    if (trace_data->h.tag != 1) {
        printf("Uncompatible endian\n");
        return 1;
    }

    if (trace_data->h.version != TRACE_VERSION) {
        printf("Uncomatible version\n");
        return 1;
    }

    fprintf(fout,"#version 2.2.0\n");
    fprintf(fout,"#creator FreeRTOS trace logger\n");
    fprintf(fout,"#createDate " __DATE__ " " __TIME__ "\n");
    fprintf(fout,"#timeScale ns\n");

    fprintf(fout,"0,Core_1,0,C,Core_1,0,set_frequence,%d\n",
            trace_data->h.core_clock);

    current_task = 0;
    if (trace_data->h.event_count != trace_data->h.max_events) {
        current_index = 0;
    } else {
        current_index = trace_data->h.current_index == 0 ?
                        trace_data->h.max_events - 1 :
                        trace_data->h.current_index - 1;
    }

    for(i = 0; i < trace_data->h.event_count; i++) {
        EVENT *event = get_event(trace_data, i);

        switch(event->types) {
            case TRACE_EVENT_TASK_SWITCHED_IN:
                fprintf(fout, "%d,%s,0,T,%s,0,%s,%s\n",
                        event->time,
                        get_taskname(trace_data, current_task),
                        get_taskname(trace_data, event->value),
                        "resume",
                        "switched_in");
                current_task = event->value;
                break;
            case TRACE_EVENT_TASK_SWITCHED_OUT:
                fprintf(fout, "%d,%s,0,T,%s,0,%s,%s\n",
                        event->time,
                        "Core_1",
                        get_taskname(trace_data, event->value),
                        "preempt",
                        "switched_out");
                current_task = event->value;
                break;
            case TRACE_EVENT_TASK_CREATE:
                fprintf(fout, "%d,%s,0,T,%s,0,%s,%s\n",
                        event->time,
                        "Core_1",
                        get_taskname(trace_data, event->value),
                        "start",
                        "task_create");
                fprintf(fout, "%d,%s,0,T,%s,0,%s,%s\n",
                        event->time,
                        "Core_1",
                        get_taskname(trace_data, event->value),
                        "preempt",
                        "task_create");
                current_task = event->value;
                break;
            case TRACE_EVENT_TASK_DELETE:
                // TODO
                /*
                fprintf(fout, "%d,%s,0,R,%s,0,%s,%s\n",
                        event->time,
                        "Core_1",
                        get_taskname(trace_data, event->value),
                        "terminate",
                        "task_delete");
                current_task = event->value;
                */
                break;
            case TRACE_EVENT_TASK_SUSPEND:
                fprintf(fout, "%d,%s,0,T,%s,0,%s,%s\n",
                        event->time,
                        get_taskname(trace_data, current_task),
                        get_taskname(trace_data, event->value),
                        "wait",
                        "task_suspend");
                current_task = event->value;
                break;
            case TRACE_EVENT_TASK_RESUME:
                fprintf(fout, "%d,%s,0,T,%s,0,%s,%s\n",
                        event->time,
                        get_taskname(trace_data, current_task),
                        get_taskname(trace_data, event->value),
                        "release",
                        "task_resume");
                current_task = event->value;
                break;
            case TRACE_EVENT_TASK_RESUME_FROM_ISR:
                fprintf(fout, "%d,%s,0,T,%s,0,%s,%s\n",
                        event->time,
                        "Core_1",
                        get_taskname(trace_data, event->value),
                        "release",
                        "resume_from_isr");
                current_task = event->value;
                break;
            case TRACE_EVENT_TASK_INCREMENT_TICK:
                // TODO
                /*
                fprintf(fout, "%d,%s,0,STI,%s,0,%s,tick_%d\n",
                        event->time,
                        "Core_1",
                        "tick_event",
                        "trigger",
                        event->value);
                */
                break;
            default:
                break;
        }
        current_index = ((current_index + 1) % trace_data->h.max_events);
    }

    fclose(fin);
    fclose(fout);
    free(trace_data);

    printf("%d events generated\n", trace_data->h.event_count);

    return 0;
}

int main(int argc, char **argv) {
    char *infile;
    char *outfile;

    if (argc != 3) {
        usage();
        exit(-1);
    }

    infile = (char*)argv[1];
    outfile = (char*)argv[2];

    gentrace(infile, outfile);

    return 0;
}

