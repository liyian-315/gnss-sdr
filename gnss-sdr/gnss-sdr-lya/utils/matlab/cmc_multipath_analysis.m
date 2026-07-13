% CMC (Code-Minus-Carrier) multipath analysis for GNSS-SDR
%
% Reads the GNSS-SDR Observables dump (set Observables.dump=true,
% Observables.dump_filename=./observables.dat in your .conf) and computes
% the Code-Minus-Carrier observable per channel, then plots:
%   1) Pseudorange and carrier-phase range time series
%   2) Raw CMC (still contains 2*ionosphere drift + ambiguity)
%   3) Detrended CMC (multipath + thermal noise estimate)
%   4) Welch PSD of detrended CMC to expose multipath fading frequencies
%   5) Per-channel summary statistics (STD, RMS, P2P)
%
% Notes:
%   * CMC = Pseudorange_m - Phase_cycles * lambda
%     => contains: 2*I (ionospheric divergence) + multipath + noise + N*lambda
%   * After removing the slow ionospheric trend, the residual is dominated by
%     multipath (low-freq, ~0.05-1 Hz fading) and receiver thermal noise (white).
%
% Usage: edit the CONFIG block below, then run.

close all; clear; clc;

if ~exist('read_hybrid_observables_dump.m', 'file')
    addpath('./libs');
end

%% ============================ CONFIG ===================================
obs_file        = './observables.dat';   % <-- CHANGE: path to observables dump
n_channels      = 5;                     % number of active channels in the run
freq_band       = 'L1';                  % 'L1' (1575.42 MHz) or 'L5' (1176.45 MHz)
detrend_method  = 'poly';                % 'poly' | 'hp'
poly_order      = 3;                     % polynomial order if detrend_method='poly'
hp_cutoff_hz    = 0.02;                  % high-pass cutoff if detrend_method='hp'
welch_window_s  = 30;                    % seconds per Welch segment
%% =======================================================================

c = 299792458;
switch upper(freq_band)
    case 'L1', f_carrier = 1575.42e6;
    case 'L5', f_carrier = 1176.45e6;
    case 'E1', f_carrier = 1575.42e6;
    case 'E5A', f_carrier = 1176.45e6;
    otherwise, error('Unknown freq_band');
end
lambda = c / f_carrier;

obs = read_hybrid_observables_dump(n_channels, obs_file);

% sample period from RX_time (first valid channel)
ref = find(any(obs.valid > 0, 2), 1, 'first');
if isempty(ref), error('No valid channel in dump.'); end
t_full = obs.RX_time(ref, :);
dt = median(diff(t_full));
fs = 1 / dt;
fprintf('Sampling rate of observables: %.2f Hz (dt=%.4f s)\n', fs, dt);

cmc_stats = table('Size',[n_channels 6], ...
    'VariableTypes',{'double','double','double','double','double','double'}, ...
    'VariableNames',{'PRN','N_samples','STD_m','RMS_m','P2P_m','FadingPeak_Hz'});

for k = 1:n_channels
    valid = obs.valid(k,:) > 0 & obs.Pseudorange_m(k,:) ~= 0;
    if nnz(valid) < 100
        fprintf('Channel %d: too few valid samples, skipped.\n', k);
        continue
    end
    t       = obs.RX_time(k, valid);
    PR      = obs.Pseudorange_m(k, valid);
    phi_m   = obs.Carrier_phase_hz(k, valid) * lambda;   % cycles -> meters
    prn     = mode(obs.PRN(k, valid));

    % --- align time origin and remove cycle-slip arcs -------------------
    t = t - t(1);
    cmc_raw = PR - phi_m;             % still has slow ionosphere + N*lambda

    % naive cycle-slip / arc detector: large jump in CMC derivative
    djump = [0 abs(diff(cmc_raw))];
    arc_break = djump > 5;            % >5 m step -> probable slip
    arc_id = cumsum(arc_break);

    cmc_detr = nan(size(cmc_raw));
    for a = unique(arc_id)
        idx = find(arc_id == a);
        if numel(idx) < 50, continue; end
        seg = cmc_raw(idx);
        switch lower(detrend_method)
            case 'poly'
                p = polyfit(t(idx), seg, poly_order);
                cmc_detr(idx) = seg - polyval(p, t(idx));
            case 'hp'
                [b,a_hp] = butter(4, hp_cutoff_hz/(fs/2), 'high');
                cmc_detr(idx) = filtfilt(b, a_hp, seg - mean(seg));
            otherwise
                error('Unknown detrend_method');
        end
    end
    finite = isfinite(cmc_detr);

    % --- statistics -----------------------------------------------------
    s = cmc_detr(finite);
    cmc_stats.PRN(k)         = prn;
    cmc_stats.N_samples(k)   = numel(s);
    cmc_stats.STD_m(k)       = std(s);
    cmc_stats.RMS_m(k)       = sqrt(mean(s.^2));
    cmc_stats.P2P_m(k)       = max(s) - min(s);

    % --- Welch PSD ------------------------------------------------------
    nwin = min(round(welch_window_s * fs), numel(s));
    if nwin < 64, nwin = max(64, floor(numel(s)/4)); end
    [Pxx, F] = pwelch(s - mean(s), hann(nwin), round(nwin/2), [], fs);
    [~, imax] = max(Pxx(F > 0.01));   % ignore DC bin
    F_pos = F(F > 0.01);
    cmc_stats.FadingPeak_Hz(k) = F_pos(imax);

    % --- Plots ----------------------------------------------------------
    figure('Name', sprintf('Ch %d  PRN %d', k-1, prn), 'NumberTitle','off');
    subplot(3,1,1);
    plot(t, PR-PR(1), 'b'); hold on;
    plot(t, phi_m-phi_m(1), 'r--'); grid on;
    legend('Pseudorange (rel)', 'Carrier-phase range (rel)');
    ylabel('m'); title(sprintf('PRN %d  range observables', prn));

    subplot(3,1,2);
    plot(t, cmc_raw - mean(cmc_raw,'omitnan'), 'k'); grid on;
    ylabel('CMC raw - mean (m)');
    title('Raw CMC (contains 2I + ambiguity + multipath + noise)');

    subplot(3,1,3);
    plot(t, cmc_detr, 'm'); grid on;
    xlabel('Time (s)'); ylabel('CMC detrended (m)');
    title(sprintf('Detrended CMC  STD=%.3f m  RMS=%.3f m  P2P=%.3f m', ...
                  cmc_stats.STD_m(k), cmc_stats.RMS_m(k), cmc_stats.P2P_m(k)));

    figure('Name', sprintf('PSD Ch %d  PRN %d', k-1, prn), 'NumberTitle','off');
    loglog(F, Pxx, 'LineWidth', 1.2); grid on;
    xlabel('Frequency (Hz)'); ylabel('PSD (m^2/Hz)');
    title(sprintf('Welch PSD of detrended CMC  PRN %d  (peak %.3f Hz)', ...
                  prn, cmc_stats.FadingPeak_Hz(k)));
end

disp('--- CMC multipath summary ---');
disp(cmc_stats);
