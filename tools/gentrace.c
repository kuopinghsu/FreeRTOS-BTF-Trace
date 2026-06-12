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
#include <inttypes.h>
#include <string.h>
#include <getopt.h>
#include <time.h>

#include "btf_trace.h"

#define VCD_SIG_RANGE (int)('~' - '!' + 1)
#define MAX_SIG_RANGE ((VCD_SIG_RANGE)*(VCD_SIG_RANGE+1))

// Packed event-word bit-field layout (32 bits): [31:24] core ID, [23:0] btf_event_t value.
#define EVENT_MASK      0x00ffffffu
#define EVENT_SHIFT     0
#define COREID_MASK     0x7f000000u
#define COREID_SHIFT    24

static int timescale = 1;

static char *get_vcdsig(
    int sig
) {
    int  a, b;
    static char str[4];

    if (sig < 0 || sig >= MAX_SIG_RANGE) {
        str[0] = '?';
        str[1] = 0;
        return str;
    }

    a = sig / VCD_SIG_RANGE;
    b = sig % VCD_SIG_RANGE;

    if (a == 0) str[1] = 0;
    else        str[1] = '!' + a - 1;
    str[0] = '!' + b;
    str[2] = 0;

    return str;
}

void usage(void) {
    printf(
        "Convert trace data to VCD or BTF format\n"
        "\n"
        "Usage: gentrace [-h] [-v|-b] [-t 0|1] inputfile outfile\n\n"
        "       -h|--help                    help\n"
        "       -b|--btf                     generate btf file (default)\n"
        "       -v|--vcd                     generate vcd file\n"
	"       -t [0|1]|--timescale [0|1]   0: timescale ns, 1: timescale us (default)\n"
        "\n"
    );
}

static uint32_t last_timestamp = 0;
static uint64_t cyc_to_time_acc = 0;

static uint64_t cyc_to_time(uint32_t timestamp, int frequency) {
    if (timestamp < last_timestamp) {
        cyc_to_time_acc += ((uint64_t)(UINT32_MAX) + 1) * (timescale ? 1000000LL : 1000000000LL) / frequency;
    }

    last_timestamp = timestamp;

    return ((uint64_t)timestamp * (timescale ? 1000000LL : 1000000000LL) / frequency) + cyc_to_time_acc;
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
    TRACE *trace_data = NULL;
    FILE *fin = NULL, *fout = NULL;
    uint32_t i;
    int *current_task;
    int current_index;
    uint64_t current_time;
    size_t result;
    long size;
    EVENT *event;
    time_t curr_time;
    struct tm* info;
    int ret = 1;

    if ((fin = fopen(infile, "rb")) == NULL) {
        printf("file %s not found\n", infile);
        goto cleanup;
    }
    if ((fout = fopen(outfile, "w")) == NULL) {
        printf("file %s can not be created\n", outfile);
        goto cleanup;
    }

    // get file size
    fseek(fin, 0, SEEK_END);
    size = ftell(fin);
    fseek(fin, 0, SEEK_SET);

    if (size <= (long)sizeof(TRACE_HEADER)) {
        printf("file too small\n");
        goto cleanup;
    }

    if ((trace_data = malloc((size_t)size)) == NULL) {
        printf("malloc error\n");
        goto cleanup;
    }

    result = fread((void*)trace_data, sizeof(char), (size_t)size, fin);
    if (result != (size_t)size) {
        printf("data read error\n");
        goto cleanup;
    }

    // Check header
    if (trace_data->h.header[0] != 'B' ||
        trace_data->h.header[1] != 'T' ||
        trace_data->h.header[2] != 'F' ||
        trace_data->h.header[3] != '2') {
        printf("The header of trace data is not correct.\n");
        goto cleanup;
    }

    // TODO: check endian. If this value is not 1, the rest values
    // should be converted to another endian. (big endian <-> little endian)
    if (trace_data->h.tag != 1) {
        printf("Incompatible endian\n");
        goto cleanup;
    }

    if (trace_data->h.version != TRACE_VERSION) {
        printf("Incompatible version\n");
        goto cleanup;
    }

    if ((current_task = malloc(sizeof(int)*trace_data->h.num_cores)) == NULL) {
        printf("malloc fail\n");
        goto cleanup;
    }

    fprintf(fout,"#version 2.2.0\n");
    fprintf(fout,"#creator FreeRTOS trace logger\n");

    // Timestamp of the start of simulation or measurement. The format has to comply
    // with "ISO 8601 extended specification for representations of dates and times"
    // YYYY-MMDDTHH:MM:SS. The time should be in UTC time (indicated by a “Z” at the
    // end)
    time(&curr_time);
    info=gmtime(&curr_time);
    fprintf(fout,"#creationDate %04d-%02d-%02dT%02d:%02d:%02dZ\n", info->tm_year+1900,
            info->tm_mon+1, info->tm_mday, info->tm_hour, info->tm_min, info->tm_sec);

    if (timescale)
        fprintf(fout,"#timeScale us\n");
    else
        fprintf(fout,"#timeScale ns\n");

    if (trace_data->h.event_count != trace_data->h.max_events) {
        current_index = 0;
    } else {
        current_index = trace_data->h.current_index;
    }

    event = get_event(trace_data, current_index);

    current_time = cyc_to_time(event->timestamp, trace_data->h.core_clock);

    for(i = 0; i < trace_data->h.num_cores; i++) {
        fprintf(fout, "%" PRIu64 ",Core_%d,0,C,Core_%d,0,set_frequency,%d\n",
               current_time, i, i, trace_data->h.core_clock);

        current_task[i] = 0;
    }

    for(i = 0; i < trace_data->h.event_count; i++) {
        event = get_event(trace_data, current_index);
        uint32_t coreid = ((uint32_t)(event->types & COREID_MASK)) >> COREID_SHIFT;

        current_time = cyc_to_time(event->timestamp, trace_data->h.core_clock);

        switch(event->types & EVENT_MASK) {
            case TRACE_EVENT_TASK_SWITCHED_IN:
                fprintf(fout, "%" PRIu64 ",[%d/%04d]%s,0,T,[%d/%04d]%s,0,%s,%s\n",
                        current_time,
                        coreid,
                        current_task[coreid], get_taskname(trace_data, current_task[coreid]),
                        coreid,
                        event->value, get_taskname(trace_data, event->value),
                        "resume",
                        "");
                break;
            case TRACE_EVENT_TASK_SWITCHED_OUT:
                fprintf(fout, "%" PRIu64 ",Core_%d,0,T,[%d/%04d]%s,0,%s,%s\n",
                        current_time,
                        coreid,
                        coreid,
                        event->value, get_taskname(trace_data, event->value),
                        "preempt",
                        "");
                current_task[coreid] = (int)event->value;
                break;
            case TRACE_EVENT_TASK_CREATE:
                fprintf(fout, "%" PRIu64 ",Core_%d,0,T,[%d/%04d]%s,0,%s,%s\n",
                        current_time,
                        coreid,
                        coreid,
                        event->value, get_taskname(trace_data, event->value),
                        "preempt",
                        "create");
                break;
            case TRACE_EVENT_TASK_DELETE:
                fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s %s[%d]\n",
                        current_time,
                        coreid,
                        "task",
                        "trigger",
                        "delete",
                        get_taskname(trace_data, event->value),
                        event->value);
                break;
            case TRACE_EVENT_TASK_SUSPEND:
                fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s %s[%d]\n",
                        current_time,
                        coreid,
                        "task",
                        "trigger",
                        "suspend",
                        get_taskname(trace_data, event->value),
                        event->value);
                break;
            case TRACE_EVENT_TASK_RESUME:
                fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s %s[%d]\n",
                        current_time,
                        coreid,
                        "task",
                        "trigger",
                        "resume",
                        get_taskname(trace_data, event->value),
                        event->value);
                break;
            case TRACE_EVENT_TASK_RESUME_FROM_ISR:
                fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s\n",
                        current_time,
                        coreid,
                        "task",
                        "trigger",
                        "resume/isr");
                break;
            case TRACE_EVENT_QUEUE_CREATE:
                switch(event->value) {
                case QUEUE_TYPE_MUTEX:
                case QUEUE_TYPE_RECURSIVE_MUTEX:
                    fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s\n",
                            current_time,
                            coreid,
                            "mutex",
                            "trigger",
                            "create");
                    break;
                case QUEUE_TYPE_COUNTING_SEM:
                case QUEUE_TYPE_BINARY_SEM:
                    fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s\n",
                            current_time,
                            coreid,
                            "sem",
                            "trigger",
                            "create");
                    break;
                default:
                    fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s\n",
                            current_time,
                            coreid,
                            "queue",
                            "trigger",
                            "create");
                }
                break;
            case TRACE_EVENT_QUEUE_SEND:
                switch(event->value) {
                case QUEUE_TYPE_MUTEX:
                case QUEUE_TYPE_RECURSIVE_MUTEX:
                    fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s\n",
                            current_time,
                            coreid,
                            "mutex",
                            "trigger",
                            "give");
                    break;
                case QUEUE_TYPE_COUNTING_SEM:
                case QUEUE_TYPE_BINARY_SEM:
                    fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s\n",
                            current_time,
                            coreid,
                            "sem",
                            "trigger",
                            "give");
                    break;
                default:
                    fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s\n",
                            current_time,
                            coreid,
                            "queue",
                            "trigger",
                            "send");
                }
                break;
            case TRACE_EVENT_QUEUE_RECEIVE:
                switch(event->value) {
                case QUEUE_TYPE_MUTEX:
                case QUEUE_TYPE_RECURSIVE_MUTEX:
                    fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s\n",
                            current_time,
                            coreid,
                            "mutex",
                            "trigger",
                            "take");
                    break;
                case QUEUE_TYPE_COUNTING_SEM:
                case QUEUE_TYPE_BINARY_SEM:
                    fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s\n",
                            current_time,
                            coreid,
                            "sem",
                            "trigger",
                            "take");
                    break;
                default:
                    fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s\n",
                            current_time,
                            coreid,
                            "queue",
                            "trigger",
                            "recv");
                }
                break;
            case TRACE_EVENT_QUEUE_DELETE:
                switch(event->value) {
                case QUEUE_TYPE_MUTEX:
                case QUEUE_TYPE_RECURSIVE_MUTEX:
                    fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s\n",
                            current_time,
                            coreid,
                            "mutex",
                            "trigger",
                            "delete");
                    break;
                case QUEUE_TYPE_COUNTING_SEM:
                case QUEUE_TYPE_BINARY_SEM:
                    fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s\n",
                            current_time,
                            coreid,
                            "sem",
                            "trigger",
                            "delete");
                    break;
                default:
                    fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s\n",
                            current_time,
                            coreid,
                            "queue",
                            "trigger",
                            "delete");
                }
                break;
            case TRACE_EVENT_TASK_INCREMENT_TICK:
                fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%d\n",
                        current_time,
                        coreid,
                        "TICK",
                        "trigger",
                        event->value);
                break;
            case TRACE_EVENT_TAG:
                fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%d\n",
                        current_time,
                        coreid,
                        "tag0_event",
                        "trigger",
                        event->value);
                break;
            case TRACE_EVENT_TAG1:
                fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%d\n",
                        current_time,
                        coreid,
                        "tag1_event",
                        "trigger",
                        event->value);
                break;
            case TRACE_EVENT_TAG2:
                fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%d\n",
                        current_time,
                        coreid,
                        "tag2_event",
                        "trigger",
                        event->value);
                break;
            case TRACE_EVENT_TAG3:
                fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%d\n",
                        current_time,
                        coreid,
                        "tag3_event",
                        "trigger",
                        event->value);
                break;
            case TRACE_EVENT_TAG4:
                fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%d\n",
                        current_time,
                        coreid,
                        "tag4_event",
                        "trigger",
                        event->value);
                break;
            case TRACE_EVENT_TAG5:
                fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%d\n",
                        current_time,
                        coreid,
                        "tag5_event",
                        "trigger",
                        event->value);
                break;
            case TRACE_EVENT_TAG6:
                fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%d\n",
                        current_time,
                        coreid,
                        "tag6_event",
                        "trigger",
                        event->value);
                break;
            case TRACE_EVENT_TAG7:
                fprintf(fout, "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%d\n",
                        current_time,
                        coreid,
                        "tag7_event",
                        "trigger",
                        event->value);
                break;
            default:
		fprintf(stderr, "Unknown event: %d\n", event->types);
		exit(1);
                break;
        }
        current_index = ((current_index + 1) % trace_data->h.max_events);
    }

    printf("BTF %d events converted\n", trace_data->h.event_count);

    ret = 0;

cleanup:
    if (fin) { fclose(fin); }
    if (fout) { fclose(fout); }
    if (trace_data) { free(trace_data); }
    return ret;
}

int genvcd(
    char *infile,
    char *outfile
) {
    TRACE *trace_data = NULL;
    FILE *fin = NULL, *fout = NULL;
    uint32_t i;
    int current_index;
    size_t result;
    long size;
    int tick_id;
    int ret = 1;

    if ((fin = fopen(infile, "rb")) == NULL) {
        printf("file %s not found\n", infile);
        goto cleanup;
    }
    if ((fout = fopen(outfile, "w")) == NULL) {
        printf("file %s can not be created\n", outfile);
        goto cleanup;
    }

    // get file size
    fseek(fin, 0, SEEK_END);
    size = ftell(fin);
    fseek(fin, 0, SEEK_SET);

    if (size <= (long)sizeof(TRACE_HEADER)) {
        printf("file too small\n");
        goto cleanup;
    }

    if ((trace_data = malloc((size_t)size)) == NULL) {
        printf("malloc error\n");
        goto cleanup;
    }

    result = fread((void*)trace_data, sizeof(char), (size_t)size, fin);
    if (result != (size_t)size) {
        printf("data read error\n");
        goto cleanup;
    }

    // Check header
    if (trace_data->h.header[0] != 'B' ||
        trace_data->h.header[1] != 'T' ||
        trace_data->h.header[2] != 'F' ||
        trace_data->h.header[3] != '2') {
        printf("The header of trace data is not correct.\n");
        goto cleanup;
    }

    // TODO: check endian. If this value is not 1, the rest values
    // should be converted to another endian. (big endian <-> little endian)
    if (trace_data->h.tag != 1) {
        printf("Incompatible endian\n");
        goto cleanup;
    }

    if (trace_data->h.version != TRACE_VERSION) {
        printf("Incompatible version\n");
        goto cleanup;
    }

    // headers
    fprintf(fout,"$version\n");
    fprintf(fout,"    FreeRTOS trace logger\n");
    fprintf(fout,"$end\n");

    if (timescale)
        fprintf(fout,"$timeScale 1us $end\n");
    else
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
        current_index = trace_data->h.current_index;
    }

    for(i = 0; i < trace_data->h.event_count; i++) {
        EVENT *event = get_event(trace_data, current_index);
	uint64_t current_time = cyc_to_time(event->timestamp, trace_data->h.core_clock);

        fprintf(fout, "#%" PRIu64 "\n", current_time);

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
                fprintf(fout, "#%" PRIu64 "\n", current_time+1);
                fprintf(fout, "0%s\n", get_vcdsig(tick_id));
                break;
            default:
                break;
        }
        current_index = ((current_index + 1) % trace_data->h.max_events);
    }

    printf("VCD %d events converted\n", trace_data->h.event_count);

    ret = 0;

cleanup:
    if (fin) { fclose(fin); }
    if (fout) { fclose(fout); }
    if (trace_data) { free(trace_data); }
    return ret;
}

int main(int argc, char **argv) {
    char *infile = NULL;
    char *outfile = NULL;
    int btf = 1;

    int c;
    const char *optstring = "hvbt:";
    struct option opts[] = {
        {"help", 0, NULL, 'h'},
        {"vcd", 0, NULL, 'v'},
        {"btf", 0, NULL, 'b'},
        {"timescale", 1, NULL, 't'}
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
            case 't':
                timescale = atoi(optarg);
                break;
            default:
                usage();
                return 1;
        }
    }

    if (argc - optind >= 2) {
        infile  = argv[optind];
        outfile = argv[optind + 1];
    }

    if (!infile || !outfile) {
        usage();
        return 1;
    }

    return btf ? genbtf(infile, outfile) : genvcd(infile, outfile);
}

