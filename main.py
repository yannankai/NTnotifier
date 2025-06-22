#!/bin/python3

import math
import os
import random
import re
import sys


#
# Complete the 'findMaximumCalories' function below.
#
# The function is expected to return a LONG_INTEGER.
# The function accepts INTEGER_ARRAY height as parameter.
#

def getMaxAlternatingMusic(music, k):
    # Write your code here
    def max_alter(music,k,start_char):
        n = len(music)
        max_len = 0
        left = 0
        flips = 0
        for right in range(n):
            if music[right] != start_char:
                flips += 1
            while flips > k:
                if music[left] != start_char:
                    flips -= 1
                left += 1
            max_len = max(max_len, right - left + 1)
            start_char  = '0' if start_char == '1' else '1'
        return max_len
    return max(max_alter(music,k,'0'),max_alter(music,k,'1'))


if __name__ == '__main__':
    print(getMaxAlternatingMusic("1000110100",2))
