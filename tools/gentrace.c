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
#include <getopt.h>

#include "btf_trace.h"

#define VCD_SIG_RANGE (int)('~' - '!' + 1)
#define MAX_SIG_RANGE (VCD_SIG_RANGE)*(VCD_SIG_RANGE+1)

static char *get_vcdsig(
    int sig
) {
    int  a, b;
    static char str[4];

    a = sig / VCD_SIG_RANGE;
    b = sig % VCD_SIG_RANGE;

    if (a == 0) str[1] = 0;
    else        str[1] = '!' + a - 1;
    str[0] = '!' + b;
    str[2] = 0;

    return (char*)&str;
}

void usage(void) {
    printf(
        "Conver trace data to VCD or BTF format\n"
        "\n"
        "Usage: [-h] [-v|-b] gentrace inputfile outfile\n\n"
        "       -h|--help       help\n"
        "       -b|--btf        generate btf file (default)\n"
        "       -v|--vcd        generate vcd file\n"
        "\n"
    );
}

static char *get_taskname(
    TRACE *trace_data,
    int index
) {
    char *ptr = (char*)&trace_data->d.task_lists;
    int n = trace_data->h.max_taskname_len * index;

    return (char*)&ptr[n];
}

static EVENT *get_event(
    TRACE *trace_data,
    int index
) {
    char *ptr = (char*)&trace_data->d.task_lists;
    int n = trace_data->h.max_tasks * trace_data->h.max_taskname_len +
            sizeof(EVENT) * index;

    return (EVENT*)&ptr[n];
}

int genbtf(
    char *infile,
    char *outfile
) {
    TRACE *trace_data;
    FILE *fin, *fout;
    int i;
    int current_task;
    int current_index;
    int result;
    EVENT *event;

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

    current_task = 0;
    if (trace_data->h.event_count != trace_data->h.max_events) {
        current_index = 0;
    } else {
        current_index = trace_data->h.current_index == 0 ?
                        trace_data->h.max_events - 1 :
                        trace_data->h.current_index;
    }

    event = get_event(trace_data, current_index);

    fprintf(fout,"%u,Core_1,0,C,Core_1,0,set_frequence,%d\n",
            event->time, trace_data->h.core_clock);

    for(i = 0; i < trace_data->h.event_count; i++) {
        event = get_event(trace_data, current_index);

        switch(event->types) {
            case TRACE_EVENT_TASK_SWITCHED_IN:
                fprintf(fout, "%u,(%04d)%s,0,T,(%04d)%s,0,%s,%s\n",
                        event->time,
                        current_task, get_taskname(trace_data, current_task),
                        event->value, get_taskname(trace_data, event->value),
                        "resume",
                        "");
                break;
            case TRACE_EVENT_TASK_SWITCHED_OUT:
                fprintf(fout, "%u,(%04d)%s,0,T,(%04d)%s,0,%s,%s\n",
                        event->time,
                        current_task, get_taskname(trace_data, current_task),
                        event->value, get_taskname(trace_data, event->value),
                        "preempt",
                        "");
                break;
            case TRACE_EVENT_TASK_CREATE:
                fprintf(fout, "%u,%s,0,T,(%04d)%s,0,%s,%s\n",
                        event->time,
                        "Core_1",
                        event->value, get_taskname(trace_data, event->value),
                        "preempt",
                        "create");
                break;
            case TRACE_EVENT_TASK_DELETE:
                // FIXME
                fprintf(fout, "%u,%s,0,R,(%04d)%s,0,%s,%s\n",
                        event->time,
                        "Core_1",
                        event->value, get_taskname(trace_data, event->value),
                        "preempt",
                        "delete");
                break;
            case TRACE_EVENT_TASK_SUSPEND:
                fprintf(fout, "%u,(%04d)%s,0,T,(%04d)%s,0,%s,%s\n",
                        event->time,
                        current_task, get_taskname(trace_data, current_task),
                        event->value, get_taskname(trace_data, event->value),
                        "wait",
                        "suspend");
                break;
            case TRACE_EVENT_TASK_RESUME:
                fprintf(fout, "%u,(%04d)%s,0,T,(%04d)%s,0,%s,%s\n",
                        event->time,
                        current_task, get_taskname(trace_data, current_task),
                        event->value, get_taskname(trace_data, event->value),
                        "release",
                        "resume");
                break;
            case TRACE_EVENT_TASK_RESUME_FROM_ISR:
                fprintf(fout, "%u,%s,0,T,(%04d)%s,0,%s,%s\n",
                        event->time,
                        "Core_1",
                        event->value, get_taskname(trace_data, event->value),
                        "release",
                        "resume/isr");
                break;
            case TRACE_EVENT_TASK_INCREMENT_TICK:
                // FIXME
                fprintf(fout, "%u,%s,0,STI,%s,0,%s,tick_%d\n",
                        event->time,
                        "Core_1",
                        "tick_event",
                        "trigger",
                        event->value);
                break;
            default:
                break;
        }
        current_task = event->value;
        current_index = ((current_index + 1) % trace_data->h.max_events);
    }

    fclose(fin);
    fclose(fout);
    free(trace_data);

    printf("%d events generated\n", trace_data->h.event_count);

    return 0;
}

int genvcd(
    char *infile,
    char *outfile
) {
    TRACE *trace_data;
    FILE *fin, *fout;
    int i;
    int current_index;
    int result;
    int tick_id;

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

    // headers
    fprintf(fout,"$version\n");
    fprintf(fout,"    FreeRTOS trace logger\n");
    fprintf(fout,"$end\n");
    fprintf(fout,"$timeScale 1ns $end\n");
    fprintf(fout,"$scope module task $end\n");

    // tick event
    tick_id = 0;
    fprintf(fout,"$var wire 1 %s %s $end\n", get_vcdsig(tick_id),
            "(0000)tick_event");

    // task lists, task number starts from 1
    for (i = 1; i <= trace_data->h.task_count; i++ ) {
        fprintf(fout,"$var wire 1 %s (%04d)%s $end\n", get_vcdsig(i), i,
                get_taskname(trace_data, i));
    }

    fprintf(fout, "$upscope $end\n");
    fprintf(fout, "$enddefinitions $end\n");
    fprintf(fout, "$dumpvars\n");

    if (trace_data->h.event_count != trace_data->h.max_events) {
        current_index = 0;
    } else {
        current_index = trace_data->h.current_index == 0 ?
                        trace_data->h.max_events - 1 :
                        trace_data->h.current_index - 1;
    }

    for(i = 0; i < trace_data->h.event_count; i++) {
        EVENT *event = get_event(trace_data, current_index);
        fprintf(fout, "#%u\n", event->time);

        switch(event->types) {
            case TRACE_EVENT_TASK_SWITCHED_IN:
                fprintf(fout, "1%s\n", get_vcdsig(event->value));
                break;
            case TRACE_EVENT_TASK_SWITCHED_OUT:
                fprintf(fout, "0%s\n", get_vcdsig(event->value));
                break;
            case TRACE_EVENT_TASK_CREATE:
                fprintf(fout, "0%s\n", get_vcdsig(event->value));
                break;
            case TRACE_EVENT_TASK_DELETE:
                fprintf(fout, "x%s\n", get_vcdsig(event->value));
                break;
            case TRACE_EVENT_TASK_SUSPEND:
                fprintf(fout, "0%s\n", get_vcdsig(event->value));
                break;
            case TRACE_EVENT_TASK_RESUME:
                fprintf(fout, "1%s\n", get_vcdsig(event->value));
                break;
            case TRACE_EVENT_TASK_RESUME_FROM_ISR:
                fprintf(fout, "1%s\n", get_vcdsig(event->value));
                break;
            case TRACE_EVENT_TASK_INCREMENT_TICK:
                fprintf(fout, "1%s\n", get_vcdsig(tick_id));
                fprintf(fout, "#%u\n", event->time+1);
                fprintf(fout, "0%s\n", get_vcdsig(tick_id));
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
    char *infile = NULL;
    char *outfile = NULL;
    int btf = 1;

    int c;
    const char *optstring = "hvb";
    struct option opts[] = {
        {"help", 0, NULL, 'h'},
        {"vcd", 0, NULL, 'v'},
        {"btf", 0, NULL, 'b'}
    };

    while((c = getopt_long(argc, argv, optstring, opts, NULL)) != -1) {
        switch(c) {
            case 'h':
                usage();
                return 1;
            case 'b':
                btf = 1;
                break;
            case 'v':
                btf = 0;
                break;
            default:
                usage();
                return 1;
        }
    }

    if (optind < argc) {
        infile = (char*)argv[optind];
        outfile = (char*)argv[optind+1];
    }

    if (!infile || !outfile) {
        usage();
        return 1;
    }

    if (btf)
        genbtf(infile, outfile);
    else
        genvcd(infile, outfile);

    return 0;
}

