import csv
import numpy as np

correct = []

with open('confidence_c.tsv') as csv_file:
    csv_reader = csv.reader(csv_file, delimiter='\t')
    line_count = 0
    for row in csv_reader:
        if line_count == 0:
            #print()
            line_count += 1
        else:
            correct.append([row[1],row[2]])
            line_count += 1
    print(line_count,"lines")


correct = np.asarray(correct)


print(correct.shape)
