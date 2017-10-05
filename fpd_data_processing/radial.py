import numpy as np
from tqdm import tqdm
from hyperspy._components.gaussian import Gaussian
from hyperspy.signals import Signal2D


def _centre_comparison(
        s, steps, step_size,
        crop_radial_signal=None, angleN=8):
    """
    Compare how the centre position affects the radial integration.
    Useful for finding on optimal centre position if one has some
    round feature. Returns a list of image stacks, one image stack
    for each centre position, and the image stack consists of radially
    integrated segments of an image.

    Currently only works with signals with 0 navigation dimensions.

    Parameters
    ----------
    s : HyperSpy 2D signal
    steps : int
    step_size : int
    crop_radial_signal : tuple, optional
    angleN : int, default 8
    """
    if s.axes_manager.navigation_dimension != 0:
        raise ValueError(
                "centre_comparison only works for pixelatedSTEM "
                "signals with 0 navigation dimensions")
    s_list = []
    centre_list = get_centre_position_list(s, steps, step_size)
    for centre_x, centre_y in centre_list:
        s_angle = s.angular_slice_radial_integration(
                angleN=angleN,
                centre_x=np.array([centre_x]),
                centre_y=np.array([centre_y]),
                show_progressbar=False)
        if crop_radial_signal is not None:
            s_angle = s_angle.isig[crop_radial_signal[0]:crop_radial_signal[1]]
        s_angle.metadata.add_node("Angle_slice_processing")
        s_angle.metadata.Angle_slice_processing.centre_x = centre_x
        s_angle.metadata.Angle_slice_processing.centre_y = centre_y
        s_list.append(s_angle)
    return(s_list)


def get_coordinate_of_min(s):
    """
    Returns the x and y values of the minimum in a signal.
    """
    z = s.data
    idx = np.argwhere(z == np.min(z))
    x = s.axes_manager[0].index2value(idx[0][1])
    y = s.axes_manager[1].index2value(idx[0][0])
    return(x, y)


def get_centre_position_list(s, steps, step_size):
    """
    Returns a zip of x and y coordinates based on the offset of the center-
    point, and number of steps in each direction and a step-size given in
    pixels. Scale and offset taken from axes_manager.
    """
    scale_x = s.axes_manager.signal_axes[0].scale
    scale_y = s.axes_manager.signal_axes[1].scale
    d1_x = scale_x*steps*step_size
    d2_x = scale_x*(steps + 1)*step_size
    d1_y = scale_y*steps*step_size
    d2_y = scale_y*(steps + 1)*step_size

    x0 = -s.axes_manager[0].offset
    y0 = -s.axes_manager[1].offset
    centre_x_list, centre_y_list = [], []
    range_x = np.arange(x0 - d1_x, x0 + d2_x, step_size*scale_x)
    range_y = np.arange(y0 - d1_y, y0 + d2_y, step_size*scale_y)
    for x in range_x:
        for y in range_y:
            centre_x_list.append(x)
            centre_y_list.append(y)
    centre_list = zip(centre_x_list, centre_y_list)
    return(centre_list)


def get_optimal_centre_position(
        s, radial_signal_span, steps=5, step_size=1, angleN=8,
        show_progressbar=True):
    """
    Find centre position of a ring by using angle sliced radial integration.

    Takes signal s, radial span of feature used to determine the centre
    position. Radially integrates the feature in angleN segments, for
    each possible centre position. Models this integrated signal
    as a Gaussian and returns array of with the standard deviations
    of these Gaussians.

    Note, the approximate centre position must be set using the offset
    parameter in the signal. The offset parameter is the negative of the
    position shown with s.plot(). So if the centre position in the image is
    x=52 and y=55:
    s.axes_manager.signal_axes[0].offset = -52
    s.axes_manager.signal_axes[1].offset = -55
    This can be checked by replotting the signal, to see if the centre
    position has the values x=0 and y=0.

    Parameters
    ----------
    s : HyperSpy 2D signal
        Only supports signals with no navigation dimensions.
    radial_signal_span : tuple
        Range for finding the circular feature.
    steps : int, default 5
        Number of steps in x/y direction to look for the optimal
        centre position. If the offset is (50, 55), and step_size 1:
        the positions x=(45, 46, 47, 48, ..., 55) and y=(50, 51, 52, ..., 60),
        will be checked.
    step_size : int, default 1
    angleN : int, default 8
        See angular_slice_radial_integration for information about angleN.

    Returns
    -------
    Optimal centre position : HyperSpy 2D signal

    Examples
    --------
    >>> import fpd_data_processing.dummy_data as dd
    >>> s = dd.get_single_ring_diffraction_signal()
    >>> s.axes_manager.signal_axes[0].offset = -105
    >>> s.axes_manager.signal_axes[1].offset = -67
    >>> import fpd_data_processing.radial as ra
    >>> s_ocp = ra.get_optimal_centre_position(s, (35, 45), steps=2)
    >>> centre_pos = ra.get_coordinate_of_min(s_ocp)

    """
    s_list = _centre_comparison(
            s, steps, step_size, crop_radial_signal=radial_signal_span,
            angleN=angleN)

    m_list = []
    for temp_s in tqdm(s_list, disable=(not show_progressbar)):
        temp_s.change_dtype('float64')
        temp_s = temp_s - temp_s.data.min()
        temp_s = temp_s/temp_s.data.max()
        am = temp_s.axes_manager
        g_centre = temp_s.inav[0].data.argmax()*am[-1].scale + am[-1].offset
        g_sigma = 3
        g_A = temp_s.data.max()*2*g_sigma

        m = temp_s.create_model()
        g = Gaussian(
                A=g_A,
                centre=g_centre,
                sigma=g_sigma)
        m.append(g)
        m.multifit(show_progressbar=False)
        m_list.append(m)
    s_centre_std_array = _get_offset_image(m_list, s, steps, step_size)
    return(s_centre_std_array)


def _get_offset_image(model_list, s, steps, step_size):
    """
    Make offset image signal based on difference in Gaussian centre position.

    Creates a Signal2D object of the standard deviation of the
    Gaussians fitted to the radially integrated features, as a
    function of center coordinate.

    Parameters
    ----------
    model_list : list of HyperSpy model objects
    s : HyperSpy 2D signal
    steps : int
    step_size : int

    Returns
    -------
    offset_signal : HyperSpy 2D signal

    """
    s_offset = Signal2D(np.zeros(shape=((steps*2)+1, (steps*2)+1)))
    am = s.axes_manager.signal_axes

    offset_x0 = -am[0].offset - (steps * step_size)
    offset_y0 = -am[1].offset - (steps * step_size)
    s_offset.axes_manager.signal_axes[0].offset = offset_x0
    s_offset.axes_manager.signal_axes[1].offset = offset_y0
    s_offset.axes_manager.signal_axes[0].scale = step_size
    s_offset.axes_manager.signal_axes[1].scale = step_size
    am_o = s_offset.axes_manager.signal_axes
    for model in model_list:
        x = model.signal.metadata.Angle_slice_processing.centre_x
        y = model.signal.metadata.Angle_slice_processing.centre_y
        std = model.components.Gaussian.centre.as_signal().data.std()
        iX, iY = am_o[0].value2index(x), am_o[1].value2index(y)
        s_offset.data[iY, iX] = std
    return s_offset
