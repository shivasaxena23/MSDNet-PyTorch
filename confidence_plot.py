import csv
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

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


correct = pd.DataFrame(data=correct)

correct[1] = correct[1].astype(float)

#print(correct[0])
correct_1 = correct[correct[0]=='0'] 
correct_2 = correct[correct[0]=='1'] 
correct_3 = correct[correct[0]=='2'] 
correct_4 = correct[correct[0]=='3'] 
correct_5 = correct[correct[0]=='4']

correct = [correct_1,correct_2,correct_3,correct_4,correct_5]



incorrect = []

with open('confidence_w.tsv') as csv_file:
    csv_reader = csv.reader(csv_file, delimiter='\t')
    line_count = 0
    for row in csv_reader:
        if line_count == 0:
            #print()
            line_count += 1
        else:
            incorrect.append([row[1],row[2]])
            line_count += 1
    print(line_count,"lines")


incorrect = pd.DataFrame(data=incorrect)

incorrect[1] = incorrect[1].astype(float)

#print(correct[0])
incorrect_1 = incorrect[incorrect[0]=='0'] 
incorrect_2 = incorrect[incorrect[0]=='1'] 
incorrect_3 = incorrect[incorrect[0]=='2'] 
incorrect_4 = incorrect[incorrect[0]=='3'] 
incorrect_5 = incorrect[incorrect[0]=='4']

incorrect = [incorrect_1,incorrect_2,incorrect_3,incorrect_4,incorrect_5]

print("\n")

def plot():
    for j in range(5):
        sns_plot = None
        sns_plot = sns.distplot(correct[j][1], color = 'blue', hist_kws={'edgecolor':'black'},label="Correct")
        sns_plot = sns.distplot(incorrect[j][1], color = 'red', hist_kws={'edgecolor':'black'},label="Incorrect")
        sns_plot.set(xlabel='Confidence', ylabel='Frequency', title="Exit : "+str(j+1))
        sns_plot.set_yticks(np.arange(0, 51, 5))
        sns_plot.legend(loc='upper left')
        fig = sns_plot.get_figure()
        fig.savefig("output_"+str(j+1)+".png")
        sns_plot.cla()

#plot()


print("Exit 1 Correct : ",correct[0].shape[0])
print("Exit 1 Incorrect : ",incorrect[0].shape[0])
print("Exit 2 Correct : ",correct[1].shape[0])                                                                                              
print("Exit 2 Incorrect : ",incorrect[1].shape[0])
print("Exit 3 Correct : ",correct[2].shape[0])                                                                                              
print("Exit 3 Incorrect : ",incorrect[2].shape[0])
print("Exit 4 Correct : ",correct[3].shape[0])                                                                                              
print("Exit 4 Incorrect : ",incorrect[3].shape[0])
print("Exit 5 Correct : ",correct[4].shape[0])                                                                                              
print("Exit 5 Incorrect : ",incorrect[4].shape[0])
print("\n")

print("Exit 1 Accuracy :", correct[0].shape[0]/(correct[0].shape[0]+incorrect[0].shape[0]))
print("Exit 2 Accuracy :", correct[1].shape[0]/(correct[1].shape[0]+incorrect[1].shape[0])) 
print("Exit 3 Accuracy :", correct[2].shape[0]/(correct[2].shape[0]+incorrect[2].shape[0])) 
print("Exit 4 Accuracy :", correct[3].shape[0]/(correct[3].shape[0]+incorrect[3].shape[0])) 
print("Exit 5 Accuracy :", correct[4].shape[0]/(correct[4].shape[0]+incorrect[4].shape[0])) 
