from io import BytesIO
from threading import RLock
from typing import Optional

from mapadroid.utils import global_variables
from mapadroid.utils.logging import LoggerEnums, get_logger

from .abstract_apk_storage import AbstractAPKStorage
from .apk_enums import APKArch, APKType
from .custom_types import MADPackages
from .utils import generate_filename
from ..db.helper.MadApkHelper import MadApkHelper

logger = get_logger(LoggerEnums.storage)


class APKStorageDatabase(AbstractAPKStorage):
    """ Storage interface for using the database.  Implements AbstractAPKStorage for ease-of-use between different
        storage mediums

    Args:
        dbc: Database wrapper

    Attributes:
        dbc: Database wrapper
        file_lock (RLock): RLock to allow updates to be thread-safe
    """
    def __init__(self, dbc):
        logger.debug('Initializing Database storage')
        self.file_lock: RLock = RLock()
        self.dbc = dbc

    async def delete_file(self, package: APKType, architecture: APKArch) -> bool:
        """ Remove the package and update the configuration

        Args:
            package (APKType): Package to lookup
            architecture (APKArch): Architecture of the package to lookup
        """
        return await MadApkHelper.delete_file(session, package, architecture)

    async def get_current_version(self, package: APKType, architecture: APKArch) -> Optional[str]:
        "Get the currently installed version of the package / architecture"
        return await MadApkHelper.get_current_version(session, package, architecture)

    async def get_current_package_info(self, package: APKType) -> Optional[MADPackages]:
        """ Get the current information for a given package.  If the package exists in the configuration but not the
            filesystem it will be removed from the configuration

        Args:
            package (APKType): Package to lookup

        Returns:
            None if no package is found.  MADPackages if the package lookup is successful
        """
        return await MadApkHelper.get_current_package_info(session, package)

    def get_storage_type(self) -> str:
        return 'db'

    async def reload(self) -> None:
        pass

    async def save_file(self, package: APKType, architecture: APKArch, version: str, mimetype: str, data: BytesIO,
                  retry: bool = False) -> bool:
        """ Save the package to the database.  Remove the old version if it existed

        Args:
            package (APKType): Package to save
            architecture (APKArch): Architecture of the package to save
            version (str): Version of the package
            mimetype (str): Mimetype of the package
            data (io.BytesIO): binary contents to be saved
            retry (bool): Not used

        Returns (bool):
            Save was successful
        """
        # TODO: Async DB accesses...
        try:
            await self.delete_file(package, architecture)
            file_length: int = data.getbuffer().nbytes
            filename: str = generate_filename(package, architecture, version, mimetype)
            insert_data = {
                'filename': filename,
                'size': file_length,
                'mimetype': mimetype,
            }
            new_id: int = self.dbc.autoexec_insert('filestore_meta', insert_data)
            insert_data = {
                'filestore_id': new_id,
                'usage': package.value,
                'arch': architecture.value,
                'version': version,
            }
            self.dbc.autoexec_insert('mad_apks', insert_data, optype='ON DUPLICATE')
            logger.info('Starting upload of APK')
            chunk_size = global_variables.CHUNK_MAX_SIZE
            for chunked_data in [data.getbuffer()[i * chunk_size:(i + 1) * chunk_size] for i in
                                 range((len(data.getbuffer()) + chunk_size - 1) // chunk_size)]:
                insert_data = {
                    'filestore_id': new_id,
                    'size': len(chunked_data),
                    'data': chunked_data.tobytes()
                }
                self.dbc.autoexec_insert('filestore_chunks', insert_data)
            logger.info('Finished upload of APK')
            return True
        except:  # noqa: E722 B001
            logger.opt(exception=True).critical('Unable to upload APK')
        return False

    async def shutdown(self) -> None:
        pass
