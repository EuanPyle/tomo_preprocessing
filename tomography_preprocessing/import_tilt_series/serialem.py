from pathlib import Path
from typing import Optional, List

import mdocfile
import pandas as pd
import rich
import starfile
import typer
from rich.progress import track

from ._cli import cli
from .. import utils


console = rich.console.Console(record=True)


@cli.command(name='SerialEM')
def import_tilt_series_from_serial_em(
        tilt_image_movie_pattern: str = typer.Option(...),
        mdoc_file_pattern: str = typer.Option(...),
        output_directory: Path = typer.Option(...),
        nominal_tilt_axis_angle: float = typer.Option(...),
        nominal_pixel_size: float = typer.Option(...),
        voltage: float = typer.Option(...),
        spherical_aberration: float = typer.Option(...),
        amplitude_contrast: float = typer.Option(...),
        dose_per_tilt_image: Optional[float] = None,
        prefix: Optional[str] = None,
        mtf_file: Optional[Path] = None,
) -> Path:
    """Import tilt-series data using SerialEM metadata.

    Parameters
    ----------
    tilt_image_movie_pattern : Filename pattern with wildcard characters
        for tilt image movie files.
    mdoc_file_pattern : Filename pattern wildcard characters for mdoc files
        containing tilt-series metadata.
    output_directory : Directory in which output files are written.
    nominal_tilt_axis_angle : Nominal tilt axis angle in the images.
    nominal_pixel_size : Nominal pixel spacing of the tilt-images in angstroms.
    voltage : Acceleration voltage (keV)
    spherical_aberration : Spherical aberration (mm)
    amplitude_contrast : Amplitude contrast fraction (e.g. 0.1)
    dose_per_tilt_image : dose in electrons per square angstrom in each tilt image.
        If set, this will override the values from the mdoc file
    prefix : a prefix which will be added to the tilt-series name.
        This avoids name collisions when processing data from multiple collection
        sessions.
    mtf_file: a text file containing the MTF of the detector.

    Returns
    -------
    tilt_series_star_file : a text file pointing to STAR files containing per tilt-series metadata
    """
    console.log('Started import_tilt_series job.')

    # Create output directory structure
    tilt_series_directory = Path(output_directory) / 'tilt_series'
    console.log(f'Creating output directory at {tilt_series_directory}')
    tilt_series_directory.mkdir(parents=True, exist_ok=True)

    # Get lists of necessary files
    tilt_image_files = list(Path().glob(tilt_image_movie_pattern))
    mdoc_files = list(Path().glob(mdoc_file_pattern))
    console.log(f'Found {len(mdoc_files)} mdoc files and {len(tilt_image_files)} image files.')

    # Get tomogram ids and construct paths for per-tilt-series STAR files
    tomogram_ids = [
        utils.mdoc.construct_tomogram_id(mdoc_file, prefix)
        for mdoc_file in mdoc_files
    ]
    tilt_series_star_files = [
        tilt_series_directory / f"{tomogram_id}.star"
        for tomogram_id in tomogram_ids
    ]

    # Construct a global dataframe pointing at per-tilt-series STAR files
    global_star_file = Path(output_directory) / 'tilt_series.star'
    global_df = pd.DataFrame({
        'rlnTomoName': tomogram_ids,
        'rlnTomoTiltSeriesStarFile': tilt_series_star_files,
    })
    starfile.write(
        data={'tilt_series': global_df},
        filename=global_star_file,
        overwrite=True
    )
    console.log(f'Wrote tilt-series data STAR file {global_star_file}')

    # Construct optics dataframe
    optics_df = pd.DataFrame({
        'rlnOpticsGroupName': [prefix],
        'rlnOpticsGroup': [1],
        'rlnVoltage': [voltage],
        'rlnSphericalAberration': [spherical_aberration],
        'rlnAmplitudeContrast': [amplitude_contrast],
        'rlnMicrographOriginalPixelSize': [nominal_pixel_size],
    })

    if mtf_file is not None:
        optics_df['rlnMtfFileName'] = mtf_file

    # Write out per tilt-series STAR files
    console.log('writing per tilt-series STAR files...')
    for mdoc_file, output_filename in track(list(zip(mdoc_files, tilt_series_star_files))):
        tilt_image_df = _generate_tilt_image_dataframe(
            mdoc_file=mdoc_file,
            tilt_image_files=tilt_image_files,
            dose_per_tilt_image=dose_per_tilt_image,
            prefix=prefix,
            nominal_tilt_axis_angle=nominal_tilt_axis_angle,
        )
        starfile.write(
            data={'optics': optics_df, 'tilt_images': tilt_image_df},
            filename=output_filename,
            overwrite=True
        )
    console.log(f'Wrote STAR files for {len(tilt_series_star_files)} tilt-series.')
    console.save_html(str(output_directory / 'log.html'), clear=False)
    console.save_text(str(output_directory / 'log.txt'), clear=False)
    return global_star_file


def _generate_tilt_image_dataframe(
        mdoc_file: Path,
        tilt_image_files: List[Path],
        prefix: str,
        nominal_tilt_axis_angle: float,
        dose_per_tilt_image: Optional[float],
) -> pd.DataFrame:
    """Generate a dataframe containing data about images in a tilt-series."""
    df = mdocfile.read(mdoc_file, camel_to_snake=True)
    df = df.sort_values(by="z_value", ascending=True)
    df = utils.mdoc.add_pre_exposure_dose(mdoc_df=df, dose_per_tilt=dose_per_tilt_image)
    df = df.sort_values(by="tilt_angle", ascending=True)
    df = utils.mdoc.add_tilt_image_files(mdoc_df=df, tilt_image_files=tilt_image_files)
    df['tilt_series_id'] = utils.mdoc.construct_tomogram_id(mdoc_file, prefix)
    df['nominal_tilt_axis_angle'] = nominal_tilt_axis_angle
    df['optics_group'] = 1

    output_df = pd.DataFrame({
        'rlnTomoName': df['tilt_series_id'],
        'rlnMicrographMovieName': df['tilt_image_file'],
        'rlnTomoTiltMovieFrameCount': df['num_sub_frames'],
        'rlnTomoTiltMovieIndex': df['z_value'],
        'rlnTomoNominalStageTiltAngle': df['tilt_angle'],
        'rlnTomoNominalTiltAxisAngle': df['nominal_tilt_axis_angle'],
        'rlnOpticsGroup': df['optics_group'],
        'rlnTomoNominalDefocus': df['target_defocus'],
        'rlnMicrographPreExposure': df['pre_exposure_dose'],
    })
    return output_df
