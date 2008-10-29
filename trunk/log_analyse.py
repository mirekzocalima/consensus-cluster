#!/usr/bin/python
# Analyse Logs

import sys

if len(sys.argv) != 3:
    print "USAGE: log_analyse.py log1 log2"
    sys.exit(0)

log1 = sys.argv[1]
log2 = sys.argv[2]

def gen_cluster_dict(log):
    clust_data = {}
    current_cluster = None
    
    f = open(log, 'r')

    for line in f:
        spl = line.strip().split()

        if spl and spl[0] == 'Cluster':
            current_cluster = spl[1]
            clust_data[current_cluster] = []

        elif line and line[0] == '\t' and current_cluster is not None:
            tspl = line.strip().split('\t')
            clust_data[current_cluster].append(tspl[0])

    return clust_data

def stats(dict1, dict2):
    #Compare all the items in dict1 to the items in dict2
    
    stat = {}
    missing = {}
    present = {}

    for clust1 in dict1:
        for clust2 in dict2:
            found = 0
            total = 0
            key = (clust1, clust2)

            for item in dict1[clust1]:
                if item in dict2[clust2]:
                    found += 1
                    present.setdefault(key, []).append(item) #Item is in both
                else:
                    missing.setdefault(key, []).append(item) #Item is in clust1, not in clust2

                total += 1

            stat[key] = found/float(total)

    for clust1 in dict1:
        relations = [ (stat[(clust1, y)], y) for y in dict2 ]
        relations.sort()

        for relation in relations:
            match_rate = relation[0]

            print "Cluster %s is related to Cluster %s, with a match rate of %s." % (clust1, relation[1], match_rate)

            key = (clust1, relation[1])
            if match_rate >= 0.75 and match_rate < 1.0:
                print "Troublemakers: %s\n" % missing[key]

            if match_rate <= 0.25 and match_rate > 0.0:
                print "Traitors: %s\n" % present[key]

def compare(log1_dict, log2_dict, log1, log2):
    print "\nComparing %s with %s:\n" % (log1, log2)
    stats(log1_dict, log2_dict)

log1_dict = gen_cluster_dict(log1)
log2_dict = gen_cluster_dict(log2)

compare(log1_dict, log2_dict, log1, log2)
compare(log2_dict, log1_dict, log2, log1)
