import hashlib
import logging
import zlib

from bitglitter.palettes.paletteutilities import _paletteGrabber
from bitglitter.protocols.protocolhandler import protocolHandler

def minimumBlockCheckpoint(blockHeightOverride, blockWidthOverride, activeFrameSizeWidth,
                           activeFrameSizeHeight):
    if blockHeightOverride and blockWidthOverride:
        if activeFrameSizeWidth < blockWidthOverride or activeFrameSizeHeight < \
                blockHeightOverride:
            logging.warning("Block override parameters are too large for a file of these dimensions.  "
                            "Aborting...")
            return False
    return True


def scanBlock(image, pixelWidth, blockWidthPosition, blockHeightPosition):
    '''This function is what's used to scan the blocks used.  First the scan area is determined, and then each of the
    pixels in that area appended to a list.  An average of those values as type int is returned.
    '''

    if pixelWidth < 5:
        startPositionX = int(blockWidthPosition * pixelWidth)
        endPositionX = int((blockWidthPosition * pixelWidth) + pixelWidth - 1)
        startPositionY = int(blockHeightPosition * pixelWidth)
        endPositionY = int((blockHeightPosition * pixelWidth) + pixelWidth - 1)

    else:
        startPositionX = int(round((blockWidthPosition * pixelWidth) + (pixelWidth * .25), 1))
        endPositionX = int(round(startPositionX + (pixelWidth * .5), 1))
        startPositionY = int(round((blockHeightPosition * pixelWidth) + (pixelWidth * .25), 1))
        endPositionY = int(round(startPositionY + (pixelWidth * .5), 1))

    scannedValues = []
    pixel = image.load()
    for xScan in range(endPositionX - startPositionX + 1):
        for yScan in range(endPositionY - startPositionY + 1):
            scannedValues.append(pixel[(startPositionX + xScan), (startPositionY + yScan)])

    redChannel = 0
    greenChannel = 0
    blueChannel = 0
    for value in scannedValues:
        redChannel += value[0]
        greenChannel += value[1]
        blueChannel += value[2]

    return (round(redChannel / len(scannedValues)), round(greenChannel / len(scannedValues)),
            round(blueChannel / len(scannedValues)))


def readInitializer(bitStream, blockHeight, blockWidth, customPaletteList, defaultPaletteList):
    '''This function decodes the raw binary data from the initializer header after verifying it's checksum, and will
    emergency stop the read if any of the conditions are met:  If the read checksum differs from the calculated
    checksum, if the read protocol version isn't supported by this BitGlitter version, if the readBlockHeight or
    readBlockWidth differ from what frameLockOn() read, or if the palette ID for the header is unknown (ie, a custom
    color which has not been integrated yet).  Returns protocolVersion and headerPalette object.'''

    # First, we're verifying the initializer is not corrupted by comparing its read checksum with a calculated one from
    # it's contents.  If they match, we continue.  If not, this frame aborts.

    logging.debug('readInitializer running...')

    bitStream.pos = 0
    fullBitStreamToHash = bitStream.read('bits : 292')
    convertedToBytes = fullBitStreamToHash.tobytes()
    calculatedCRC = zlib.crc32(convertedToBytes)
    readCRC = bitStream.read('uint : 32')
    if calculatedCRC != readCRC:
        logging.warning('Initializer checksum failure.  Aborting...')
        return False, False

    bitStream.pos = 0
    protocolVersion = bitStream.read('uint : 4')
    if str(protocolVersion) not in protocolHandler.availableProtocols:
        logging.warning(f'Protocol v{str(protocolVersion)} not supported in this version of BitGlitter.  Please update '
                        f'to fix.  Aborting...')
        return False, False

    readBlockHeight = bitStream.read('uint : 16')
    readBlockWidth = bitStream.read('uint : 16')
    if readBlockHeight != blockHeight or readBlockWidth != blockWidth:
        logging.warning('readInitializer: Geometry assertion failure.  Aborting...')
        logging.debug(f'readBlockHeight: {readBlockHeight}\n blockHeight {blockHeight}'
                      f'\n readBlockWidth {readBlockWidth}\n blockWidth {blockWidth}')
        return False, False

    bitStream.pos += 248
    framePaletteID = bitStream.read('uint : 8')

    if framePaletteID > 100:

        bitStream.pos -= 256
        framePaletteID = bitStream.read('hex : 256')
        framePaletteID.lower()

        if framePaletteID not in customPaletteList:

            logging.warning('readInitializer: This header palette is unknown, reader cannot proceed.  This can occur'
                            ' if the creator of the stream uses a non-default palette.\nAborting...')
            return False, False
    else:

        if str(framePaletteID) not in defaultPaletteList:
            logging.warning('readInitializer: This default palette is unknown by this version of BitGlitter.  This\n'
                            "could be the case if you're using an older version.  Aborting...")
            logging.debug(f'framePaletteID: {framePaletteID}\ndefaultPaletteList: {defaultPaletteList}')
            return False, False
    framePalette = _paletteGrabber(str(framePaletteID))

    logging.debug('readInitializer successfully ran.')
    return protocolVersion, framePalette


def readFrameHeader(bitStream):
    '''While readInitializer is mostly used for verification of values, this function's purpose is to return values
    needed for the reading process, once verified.  Returns streamSHA, frameSHA, frameNumber, and blocksToRead.'''

    logging.debug('readFrameHeader running...')
    fullBitStreamToHash = bitStream.read('bytes : 72')

    calculatedCRC = zlib.crc32(fullBitStreamToHash)
    readCRC = bitStream.read('uint : 32')
    if calculatedCRC != readCRC:
        logging.warning('frameHeader checksum failure.  Aborting...')
        return False, False, False, False

    bitStream.pos = 0
    streamSHA = bitStream.read('hex : 256')
    frameSHA = bitStream.read('hex : 256')
    frameNumber = bitStream.read('uint : 32')
    blocksToRead = bitStream.read('uint : 32')

    logging.debug('readFrameHeader successfully ran.')
    return streamSHA, frameSHA, frameNumber, blocksToRead


def validatePayload(payloadBits, readFrameSHA):
    shaHasher = hashlib.sha256()
    shaHasher.update(payloadBits.tobytes())
    stringOutput = shaHasher.hexdigest()
    logging.debug(f'length of payloadBits: {payloadBits.len}')
    if stringOutput != readFrameSHA:
        logging.warning('validatePayload: readFrameSHA does not match calculated one.  Aborting...')
        logging.debug(f'Read from frameHeader: {readFrameSHA}\nCalculated just now: {stringOutput}')
        return False
    logging.debug('Payload validated this frame.')
    return True


def returnStreamPalette(streamPaletteID, isCustom, customColorName, customColorDescription, customColorDateCreated,
                        customColorPalette):
    logging.debug('Returning stream palette...')
    if isCustom == False:
        try:
            returnPalette = _paletteGrabber(str(streamPaletteID))
            logging.debug(f'Default palette ID {streamPaletteID} successfully loaded!')
            return returnPalette
        except:
            logging.warning(f'This version of BitGlitter does not have default palette {streamPaletteID}.  Please update '
                            f'it to a\nnewer version!')

    else:
        pass
    #first, we see if the palette exists.  if not, we'll go through the process of making it.
    #todo do


#todo, look at all of this.... some of it may not be needed in light of partialsave functionality