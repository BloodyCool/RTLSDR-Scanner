#
# rtlsdr_scan
#
# http://eartoearoak.com/software/rtlsdr-scanner
#
# Copyright 2012 - 2014 Al Brown
#
# A frequency scanning GUI for the OsmoSDR rtl-sdr library at
# http://sdr.osmocom.org/trac/wiki/rtl-sdr
#
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
from collections import OrderedDict
import datetime
from decimal import Decimal
from operator import itemgetter, mul
import time

from matplotlib.dates import date2num, seconds
import numpy

from misc import db_to_level, level_to_db


class Extent():
    def __init__(self, spectrum):
        self.clear()
        self.calc_extent(spectrum)

    def clear(self):
        self.fMin = float('inf')
        self.fMax = float('-inf')
        self.lMin = float('inf')
        self.lMax = float('-inf')
        self.tMin = float('inf')
        self.tMax = float('-inf')
        self.fPeak = None
        self.lPeak = None
        self.tPeak = None

    def calc_extent(self, spectrum):
        for timeStamp in spectrum:
            points = spectrum[timeStamp].items()
            if len(points) > 0:
                fMin = min(points, key=itemgetter(0))[0]
                fMax = max(points, key=itemgetter(0))[0]
                lMin = min(points, key=itemgetter(1))[1]
                lMax = max(points, key=itemgetter(1))[1]
                self.fMin = min(self.fMin, fMin)
                self.fMax = max(self.fMax, fMax)
                self.lMin = min(self.lMin, lMin)
                self.lMax = max(self.lMax, lMax)
        self.tMin = min(spectrum)
        self.tMax = max(spectrum)
        self.tPeak = self.tMax
        if len(spectrum[self.tMax]) > 0:
            self.fPeak, self.lPeak = max(spectrum[self.tMax].items(),
                                         key=lambda(_f, l): l)

    def get_f(self):
        if self.fMin == self.fMax:
            return self.fMin, self.fMax - 0.001
        return self.fMin, self.fMax

    def get_l(self):
        if self.lMin == self.lMax:
            return self.lMin, self.lMax - 0.001
        return self.lMin, self.lMax

    def get_t(self):
        return epoch_to_mpl(self.tMax), epoch_to_mpl(self.tMin - 1)

    def get_ft(self):
        tExtent = self.get_t()
        return [self.fMin, self.fMax, tExtent[0], tExtent[1]]

    def get_peak_fl(self):
        return self.fPeak, self.lPeak

    def get_peak_flt(self):
        return self.fPeak, self.lPeak, self.tPeak


class Measure():
    MIN, MAX, AVG, GMEAN, HBW, OBW = range(6)

    def __init__(self, spectrum, start, end):
        self.isValid = False
        self.minF = None
        self.maxF = None
        self.minP = None
        self.maxP = None
        self.avgP = None
        self.gMeanP = None
        self.flatness = None
        self.hbw = None
        self.obw = None

        self.calculate(spectrum, start, end)

    def calculate(self, spectrum, start, end):
        sweep = slice_spectrum(spectrum, start, end)
        if sweep is None or len(sweep) == 0:
            return

        self.minF = min(sweep)[0]
        self.maxF = max(sweep)[0]
        self.minP = min(sweep, key=lambda v: v[1])
        self.maxP = max(sweep, key=lambda v: v[1])

        powers = [Decimal(db_to_level(p[1])) for p in sweep]
        length = len(powers)

        avg = sum(powers, Decimal(0)) / length
        self.avgP = level_to_db(avg)

        product = reduce(mul, iter(powers))
        gMean = product ** (Decimal(1.0) / length)
        self.gMeanP = level_to_db(gMean)

        self.flatness = gMean / avg

        self.calc_hbw(sweep)
        self.calc_obw(sweep)

        self.isValid = True

    def calc_hbw(self, sweep):
        power = self.maxP[1] - 3
        self.hbw = [None, None, power]

        if power >= self.minP[1]:
            for (f, p) in sweep:
                if p >= power:
                    self.hbw[0] = f
                    break
            for (f, p) in reversed(sweep):
                if p >= power:
                    self.hbw[1] = f
                    break

    def calc_obw(self, sweep):
        self.obw = [None, None, None]

        totalP = 0
        for (_f, p) in sweep:
            totalP += p
        power = totalP * 0.005
        self.obw[2] = power

        if power >= self.minP[1]:
            for (f, p) in sweep:
                if p >= power:
                    self.obw[0] = f
                    break
            for (f, p) in reversed(sweep):
                if p >= power:
                    self.obw[1] = f
                    break

    def is_valid(self):
        return self.isValid

    def get_f(self):
        return self.minF, self.maxF

    def get_min_p(self):
        return self.minP

    def get_max_p(self):
        return self.maxP

    def get_avg_p(self):
        return self.avgP

    def get_gmean_p(self):
        return self.gMeanP

    def get_flatness(self):
        return self.flatness

    def get_hpw(self):
        return self.hbw

    def get_obw(self):
        return self.obw


def count_points(spectrum):
    points = 0
    for timeStamp in spectrum:
            points += len(spectrum[timeStamp])

    return points


def reduce_points(spectrum, limit):
    total = count_points(spectrum)
    if total < limit:
        return spectrum

    newSpectrum = OrderedDict()
    ratio = float(total) / limit
    for timeStamp in spectrum:
        points = spectrum[timeStamp].items()
        reduced = OrderedDict()
        for i in xrange(int(len(points) / ratio)):
            point = points[int(i * ratio):int((i + 1) * ratio)][0]
            reduced[point[0]] = point[1]
        newSpectrum[timeStamp] = reduced

    return newSpectrum


def split_spectrum(spectrum):
    freqs = spectrum.keys()
    powers = map(spectrum.get, freqs)

    return freqs, powers


def split_spectrum_sort(spectrum):
    freqs = spectrum.keys()
    freqs.sort()
    powers = map(spectrum.get, freqs)

    return freqs, powers


def slice_spectrum(spectrum, start, end):
    if spectrum is None or start is None or end is None or len(spectrum) < 1:
        return None

    sweep = spectrum[max(spectrum)]
    if len(sweep) == 0:
        return None

    if min(sweep) > start or max(sweep) < end:
        length = len(spectrum)
        if length > 1:
            sweep = spectrum.values()[length - 2]
        else:
            return None

    sweepTemp = {}
    for f, p in sweep.iteritems():
        if start <= f <= end:
            sweepTemp[f] = p
    return sorted(sweepTemp.items(), key=lambda t: t[0])


def create_mesh(spectrum, mplTime):
    total = len(spectrum)
    width = len(spectrum[min(spectrum)])
    x = numpy.empty((width, total + 1)) * numpy.nan
    y = numpy.empty((width, total + 1)) * numpy.nan
    z = numpy.empty((width, total + 1)) * numpy.nan

    j = 1
    for ys in spectrum:
        time = epoch_to_mpl(ys) if mplTime else ys
        xs, zs = split_spectrum(spectrum[ys])
        for i in range(len(xs)):
            x[i, j] = xs[i]
            y[i, j] = time
            z[i, j] = zs[i]
        j += 1

    x[:, 0] = x[:, 1]
    if mplTime:
        y[:, 0] = y[:, 1] - seconds(1)
    else:
        y[:, 0] = y[:, 1] - 1
    z[:, 0] = z[:, 1]

    return x, y, z


def sort_spectrum(spectrum):
    newSpectrum = OrderedDict()
    for timeStamp in reversed(sorted(spectrum)):
        newPoints = OrderedDict()
        points = sorted(spectrum[timeStamp].items())
        for point in points:
            newPoints[point[0]] = point[1]
        newSpectrum[timeStamp] = newPoints

    return newSpectrum


def epoch_to_local(epoch):
    local = time.localtime(epoch)
    return time.mktime(local)


def epoch_to_mpl(epoch):
    epoch = epoch_to_local(epoch)
    dt = datetime.datetime.fromtimestamp(epoch)
    return date2num(dt)
