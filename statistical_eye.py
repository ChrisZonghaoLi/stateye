import numpy as np
import os
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import norm
from scipy.signal import argrelextrema

import seaborn as sns

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.ticker import FormatStrFormatter
plt.style.use(style='default')
plt.rcParams['font.family']='calibri'


def statistical_eye(pulse_response, 
                                samples_per_symbol=128, 
                                window_size=128, 
                                vh_size=2048, 
                                M=4, 
                                A_window_multiplier=2, 
                                sample_size=16,
                                mu_noise=0, 
                                sigma_noise=1.33e-4, 
                                mu_jitter=1.6,#0.025 UI, 
                                sigma_jitter=1.92, #0.015 UI 
                                target_BER=2.4e-4,
                                noise_flag=False,
                                jitter_flag=False,
                                plot=False,
                                pdf_conv_flag=True,
                                diff_signal=True,
                                **kwargs):
    
    # https://www.oiforum.com/wp-content/uploads/2019/01/OIF-CEI-04.0.pdf
    # implementation of statistical eye diagram with the inclusion of noise and jitter
    # M = 4
    # sigma_noise = 1.327780102275975e-4
    # # choose a vh step  such that the pdf does not vary much with x
    # vh_size = 2048 # in matlab this number is 2049
    # window_size = 128
    # sample_size = 9
    
    # print(pulse_response)
    pulse_response = np.array(pulse_response)
    pulse_response_DC = pulse_response[0]
    pulse_response = pulse_response - pulse_response_DC # remove DC offset
    window = [i for i, e in enumerate(pulse_response) if e != 0] # window that extracts the pulse  
    window_start, window_end = window[0]-1, window[-1]+1
    if diff_signal == True:
        pulse_input = pulse_response[window_start : window_end] * 0.5  # considering differential signaling
    else:
        pulse_input = pulse_response[window_start : window_end]  # considering signal-ended signaling
    idx_main = np.argmax(abs(pulse_input)) # this is the c0, main cursor, from OIF doc, see section 2.C.5 and 2.B.2
    # print(f'idx_main: {idx_main}')

    
    if M == 2:
        d = np.array([-1, 1]).reshape(1,M) # direction of pulse polarity
        if pdf_conv_flag == False and sample_size >= 16:
            sample_size = 16
    elif M == 4:
        d = np.array([-1, -1/3, 1/3, 1]).reshape(1,M)  # direction of pulse polarity
        if pdf_conv_flag == False and sample_size >= 9:
            sample_size = 9
    else:
        print('M has to be either 2 or 4.')

    A_window_min = abs(pulse_input[idx_main]) * -A_window_multiplier
    A_window_max = abs(pulse_input[idx_main]) * A_window_multiplier
    mybin_edges = np.linspace(A_window_min, A_window_max, vh_size+1) # my bin edges
    vh = 0.5*(mybin_edges[1:] + mybin_edges[:-1])
    
    pdf_list = []
    # using convolution to find the ISI pdf over the entire pulse response is faster than finding the all combinations then finding the histogram
    for idx in range(-int(window_size/2),int(window_size/2)):
        idx_sampled = idx_main+idx
        sampled_points = []
        
        # i=0 tp include the sampled main cursor, points were sampled around the main coursor
        i = 0
        while idx_sampled - i*samples_per_symbol >= 0:
            sampled_points.append(idx_sampled - i*samples_per_symbol)
            i = i + 1
    
        # i=1 tp exclude the sampled main cursor, points were sampled around the main coursor
        j = 1 
        while idx_sampled + j*samples_per_symbol <= len(pulse_input)-1:
            sampled_points.append(idx_sampled + j*samples_per_symbol)
            j = j + 1
    
        sampled_points = sampled_points[:sample_size]
        sampled_amps = np.array([pulse_input[i] for i in sampled_points]).reshape(-1,1)
        sampled_amps = sampled_amps @ d 
        
        if pdf_conv_flag == True:
            pdf, _ = np.histogram(sampled_amps[0], mybin_edges) 
            pdf = pdf/sum(pdf)
            
            for j in range(1, len(sampled_amps)):
                pdf_cursor, _ = np.histogram(sampled_amps[j], mybin_edges)
                pdf_cursor = pdf_cursor/sum(pdf_cursor)
                pdf = np.convolve(pdf, pdf_cursor, mode='same')
                pdf = pdf/sum(pdf)
            
            pdf_list.append(pdf)
            
        if pdf_conv_flag == False:
            all_combs = np.array(np.meshgrid(*[sampled_amps[i] for i in range(len(sampled_amps))])).T.reshape(-1,len(sampled_amps))
            A = np.sum(all_combs, axis=1)
            pdf, _ = np.histogram(A, mybin_edges)
            pdf = pdf/sum(pdf)
            pdf_list.append(pdf)
        
    ####################### noise inclusion ###########################
    hist_list = []
    if noise_flag == True:
        # mu_noise = 0
        noise_pdf = norm.pdf(vh, mu_noise, sigma_noise)
        noise_pdf = noise_pdf/sum(noise_pdf)
        for i in range(window_size):
            pdf = pdf_list[i]
            pdf = np.convolve(noise_pdf, pdf, mode='same')
            hist_list.append(pdf)
    else:
        hist_list = pdf_list
    
    ####################### jitter inclusion ###########################
    # deterministic jitter, implemented as a dual dirac function
    jitter_xaxis_step_size = 1 # typically it should be smaller than <samples_per_symbol * 0.01>
    x_axis = np.linspace(-(window_size-1), window_size-1, int(2*(window_size-1)/jitter_xaxis_step_size)+1) 
    idx_middle = int((len(x_axis)-1)/2) 
    num_steps = int(1/jitter_xaxis_step_size)
    
    # https://e2e.ti.com/blogs_/b/analogwire/posts/timing-is-everything-jitter-specifications
    # mu_jitter = samples_per_symbol * 0.1 # a typical mu 
    # sigma_jitter = samples_per_symbol * 0.015 # by default for about 2.4e-4 BER rate
    jitter_pdf1 = norm.pdf(x_axis, -mu_jitter, sigma_jitter)
    jitter_pdf2 = norm.pdf(x_axis, mu_jitter, sigma_jitter)

    jitter_pdf = (jitter_pdf1 + jitter_pdf2) / sum(jitter_pdf1 + jitter_pdf2)
    # plt.plot(x_axis, jitter_pdf)
    
    if jitter_flag == True:
        for i in range(window_size):
            pdf = np.zeros(vh_size)
            for j in range(window_size):
                # sliding the window from index = -(idx-j) till end
                # print(idx_middle + (-(i-j)) * num_steps)
                if jitter_xaxis_step_size < 1:
                    joint_pdf = hist_list[j] * np.trapz(jitter_pdf[idx_middle+(j-i)*num_steps : idx_middle+(j-i+1)*num_steps], x_axis[idx_middle+(j-i)*num_steps : idx_middle+(j-i+1)*num_steps])  
                if jitter_xaxis_step_size == 1:
                    joint_pdf = hist_list[j] * jitter_pdf[idx_middle+(j-i)*num_steps]
                pdf = pdf + joint_pdf
    
            pdf = pdf/sum(pdf)
            hist_list[i] = pdf # overwrite the jitter included pdf

    ##################### contour ########################
    
    hist_list = np.array(hist_list).T
    # find all voltage level at eye centers
    A_pulse_max = pulse_input[idx_main]  
    if A_pulse_max >= 0:
        A_levels = A_pulse_max * d[0] * -1 # simply for consistency: we want this list to go from positive voltage levels to negative levels
    else: 
        A_levels = A_pulse_max * d[0] 
    
    if M == 4:
        if A_pulse_max >= 0: # same reason as above
            eye_center_levels = A_pulse_max * np.array([-2/3, 0, 2/3]) * -1
        else:
            eye_center_levels = A_pulse_max * np.array([-2/3, 0, 2/3])
    if M == 2:
        eye_center_levels = A_pulse_max * np.array([0])
    
    # print(eye_center_levels)
    # find all signal voltage level idx at which vertical index
    idx_A_levels_yaxis = []
    for i in range(len(A_levels)):
        idx_line_horizontal =  (np.abs(vh-A_levels[i])).argmin()
        idx_A_levels_yaxis.append(idx_line_horizontal)
        
    # find the idx of eye center on voltage axis (y-axis)
    idx_eye_center_levels_yaxis = []  # this is the idx of eye center on voltage axis
    for i in range(len(eye_center_levels)):
        idx_line_horizontal =  (np.abs(vh-eye_center_levels[i])).argmin()
        idx_eye_center_levels_yaxis.append(idx_line_horizontal)
        
    contour_list = []
    
    for i in range(window_size):
        if M == 2:
            # 1
            cdf_1 = np.cumsum(hist_list[idx_eye_center_levels_yaxis[0]:,i])
            # 0
            cdf_0 = np.cumsum(np.flip(hist_list[:idx_eye_center_levels_yaxis[0],i]))
            contour = np.concatenate((np.flip(cdf_0), cdf_1))
        if M == 4:
            # 11:
            cdf_11 = np.cumsum(hist_list[idx_eye_center_levels_yaxis[0]:,i])
            # 10:
            cdf_10_part1 = np.cumsum(np.flip(hist_list[idx_A_levels_yaxis[1]:idx_eye_center_levels_yaxis[0],i]))
            cdf_10_part2 = np.cumsum(hist_list[idx_eye_center_levels_yaxis[1]:idx_A_levels_yaxis[1],i])
            # 01:
            cdf_01_part1 = np.cumsum(np.flip(hist_list[idx_A_levels_yaxis[2]:idx_eye_center_levels_yaxis[1],i]))
            cdf_01_part2 = np.cumsum(hist_list[idx_eye_center_levels_yaxis[2]:idx_A_levels_yaxis[2],i])
            # 00:
            cdf_00 = np.cumsum(np.flip(hist_list[:idx_eye_center_levels_yaxis[2],i]))
        
            contour = np.concatenate((np.flip(cdf_00), cdf_01_part2, np.flip(cdf_01_part1), cdf_10_part2, np.flip(cdf_10_part1), cdf_11))
            # print(contour.shape)

        contour_list.append(contour)
         
    contour_list = np.array(contour_list).T
    eye = np.array(hist_list)

    ################### contour widths ####################
    try:
        idx_below_BER_horizontal_list = []
        for i in range(len(eye_center_levels)):
            contour_eye_center_horizontal = contour_list[idx_eye_center_levels_yaxis[i], :]
            idx_below_BER_horizontal = np.where(np.diff(np.signbit(contour_eye_center_horizontal-target_BER)))[0]
            idx_below_BER_horizontal_list.append(idx_below_BER_horizontal)
            
        # print(idx_eye_center_levels_yaxis)
        # print(idx_below_BER_horizontal_list)
        
        # we have to find out where the time center of the center eye first
        if M == 2:
            idx_below_BER_horizontal_center = idx_below_BER_horizontal_list[0]
        if M == 4:
            idx_below_BER_horizontal_up = idx_below_BER_horizontal_list[0]
            idx_below_BER_horizontal_center = idx_below_BER_horizontal_list[1]
            idx_below_BER_horizontal_low = idx_below_BER_horizontal_list[2]
    
        _width_center = np.diff(idx_below_BER_horizontal_center)
        _idx1_width_center = np.argmax(_width_center) # make an assumption here: the biggest with jump on the horizontal center line is the center eye width
        _idx2_width_center = _idx1_width_center + 1
        eye_width_center = idx_below_BER_horizontal_center[_idx2_width_center] - idx_below_BER_horizontal_center[_idx1_width_center]
        idx_eye_center_xaxis = idx_below_BER_horizontal_center[_idx1_width_center] + int(eye_width_center/2)
        
        if M == 2:
            eye_widths = [eye_width_center]
        if M == 4:
            _idx1_width_up = np.where(np.diff(np.signbit(idx_below_BER_horizontal_up-idx_eye_center_xaxis)))[0][0]
            _idx2_width_up = _idx1_width_up + 1
            eye_width_up = idx_below_BER_horizontal_up[_idx2_width_up] - idx_below_BER_horizontal_up[_idx1_width_up]
            
            _idx1_width_low = np.where(np.diff(np.signbit(idx_below_BER_horizontal_low-idx_eye_center_xaxis)))[0][0]
            _idx2_width_low = _idx1_width_low + 1
            eye_width_low = idx_below_BER_horizontal_low[_idx2_width_low] - idx_below_BER_horizontal_low[_idx1_width_low]
    
            eye_widths = [eye_width_up, eye_width_center, eye_width_low]
    
        eye_widths_mean = np.mean(eye_widths)
        # print(idx_eye_center_xaxis)
        # print(eye_widths)
    except:
        eye_widths_mean = 0
        if M == 4:
            eye_widths = [0, 0, 0]
        if M == 2:
            eye_widths = 0
            
    ################ contour heights, distortion heights and COM #################
    
    try:
        contour_eye_center_vertical = contour_list[:, idx_eye_center_xaxis]
        idx_below_BER_vertical = np.where(np.diff(np.signbit(contour_eye_center_vertical-target_BER)))[0]
        # print(idx_below_BER_vertical)
        
        eye_heights = []
        for j in range(0, 2*(M-1), 2): # it finds the BER contour heights from the vertical line
            _idx1_eye_height = idx_below_BER_vertical[j]
            _idx2_eye_height = idx_below_BER_vertical[j+1]
            eye_height = vh[_idx2_eye_height] - vh[_idx1_eye_height]
            eye_heights.append(eye_height)
    
        eye_heights = np.flip(eye_heights) # so that it is from up eye to bottom eye
        eye_heights_mean = np.mean(eye_heights)
    
        # distortion heights #
    
        idx_distortion = idx_below_BER_vertical.copy()
        idx_distortion = np.insert(idx_distortion, 0, idx_A_levels_yaxis[-1])
        idx_distortion = np.append(idx_distortion, idx_A_levels_yaxis[0])
        
        distortion_heights = []
        for i in range(0, 2*M, 2):
            idx1_distortion = idx_distortion[i] 
            idx2_distortion = idx_distortion[i+1] 
            distortion_height = vh[idx2_distortion] - vh[idx1_distortion]
            distortion_heights.append(distortion_height)
    
        distortion_heights = np.flip(distortion_heights) # so that it is from up eye to bottom eye
        distortion_heights_mean = np.mean(distortion_heights)
        
        # COM #
        COM = 20*np.log10((A_levels[0]-A_levels[-1])/np.sum(distortion_heights))

    except:
        COM = 0   
        distortion_heights = A_levels
        distortion_heights_mean = np.mean(distortion_heights)
        if M == 4:
            eye_heights = [0, 0, 0]
        if M == 2:
            eye_heights = 0
        eye_heights_mean = 0

    ##################### plot eye diagram ##########################
    # show heat map of the eye diagram
    # https://stackoverflow.com/questions/33282368/plotting-a-2d-heatmap-with-matplotlib
    # plot = True
    if plot == True:
        fig, ax = plt.subplots(1,1)
        eye_df = pd.DataFrame(eye, index=np.around(np.flip(vh)*1e3, 2), columns=np.around(np.arange(int(-window_size/2), int(window_size/2))/samples_per_symbol, 2))    
        heatmap = sns.heatmap(data=eye_df, ax=ax, cmap='rainbow')
        contour_plot = ax.contour(np.arange(0.5, window_size), np.arange(0.5, vh.shape[0]), np.array(contour_list), levels=[target_BER], colors='yellow')
        ax.clabel(contour_plot, inline=True)
        if noise_flag == True and jitter_flag == False:
            ax.set_title('$\mu_{{noise}}$={:.2e} samples | $\sigma_{{noise}}$={:.2e} V'.format(mu_noise, sigma_noise))
        elif jitter_flag == True and noise_flag == False:
            ax.set_title('$\mu_{{jitter}}$={:.2e} UI | $\sigma_{{jitter}}$={:.2e} UI'.format(mu_jitter/samples_per_symbol, sigma_jitter/samples_per_symbol))
        elif jitter_flag == True and noise_flag == True:
            ax.set_title('$\mu_{{noise}}$={:.2e} V | $\sigma_{{noise}}$={:.2e} V | $\mu_{{jitter}}$={:.2e} samples | $\sigma_{{jitter}}$={:.2e} samples'.format(mu_noise, sigma_noise, mu_jitter, sigma_jitter))
        else:
            ax.set_title('Statistical Eye without Jitter or Noise')
        
        ax.set_ylabel('voltage (mV)')
        ax.set_xlabel('time (UI)')
        plt.show()
        
    return{'center_COM': COM,
               'eye_heights': eye_heights,
               'eye_heights_mean': eye_heights_mean,
               'distortion_heights': distortion_heights,
               'distortion_heights_mean': distortion_heights_mean,
               'eye_widths': eye_widths,
               'eye_widths_mean': eye_widths_mean,
               'A_levels': A_levels,
               'eye_center_levels': eye_center_levels,
               'stateye': eye
        }