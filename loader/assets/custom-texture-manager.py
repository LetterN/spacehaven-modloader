import math
import os
from typing import List, Dict

import lxml.etree
import png
import rectpack


class RegisteredTexture:
    """All the metadata needed to construct a region node."""
    ParentMod: str
    TexPath: str
    CoreRegionID: int
    FileSizeX: int
    FileSizeY: int

    def __init__(self, mod: str, texPath: str, regionID: int):
        self.ParentMod = mod
        self.TexPath = texPath
        self.CoreRegionID = regionID

        filepath = TextureManager.getModTexturePath(self.ParentMod, self.TexPath)
        (w, h, rows, info) = png.Reader(filepath).asRGBA()

        self.FileSizeX = w
        self.FileSizeY = h

    def __str__(self):
        return f"[{self.CoreRegionID:0>5}] {self.ParentMod}: {self.TexPath} - ({self.FileSizeX}, {self.FileSizeY})"


RegTexLibrary = List[RegisteredTexture]

class TextureManager:
    _TexFileResolution = 2000
    _RegionIdLastCore = 0
    _RegionIdNextOffset = 1

    RegisteredTexturesCustomRegion : RegTexLibrary = []
    RegisteredTexturesCoreRegion : RegTexLibrary = []
    RegisteredModPaths : Dict[str, str] = dict()
    RemappedRegionIDs : Dict[int, int] = dict()
    CustomTextureIDStart = 400

    Packer : rectpack.PackerGlobal = None

    @classmethod
    def setup(cls, lastCoreRegionID: int):
        cls._RegionIdLastCore = lastCoreRegionID

    @classmethod
    def registerNewTexture(cls, mod: str, texPath: str, regionID: int = -1):
        if cls.isCoreRegion(regionID):
            tmp = RegisteredTexture(mod, texPath, regionID)
            cls.RegisteredTexturesCoreRegion.append(tmp)
        else:
            if regionID != -1 and regionID in cls.RemappedRegionIDs:
                raise KeyError(f"Cannot remap ID {regionID}: Already remapped!")
            rid = cls.popNextRegionID()
            tmp = RegisteredTexture(mod, texPath, rid)
            cls.RegisteredTexturesCustomRegion.append(tmp)
            cls.RemappedRegionIDs[regionID] = rid

    @classmethod
    def pack(cls):
        packer = rectpack.newPacker(rotation=False)
        cls.Packer = packer

        # as many bins as needed
        packer.add_bin(cls._TexFileResolution, cls._TexFileResolution, float("inf"))

        for rt in cls.RegisteredTexturesCustomRegion:
            rt: RegisteredTexture
            packer.add_rect(rt.FileSizeX, rt.FileSizeY, cls.RegisteredTexturesCustomRegion.index(rt))

        packer.pack()

    @classmethod
    def popNextRegionID(cls):
        """Get next region ID and increment the counter"""
        tmp = cls._RegionIdLastCore + cls._RegionIdNextOffset
        cls._RegionIdNextOffset += 1
        return tmp

    @classmethod
    def isCoreRegion(cls, rID: int):
        return rID > -1 and rID <= cls._RegionIdLastCore

    @classmethod
    def getModTexturePath(cls, mod: str, texPath: str):
        if mod not in cls.RegisteredModPaths:
            texFolderPath = os.path.join(mod, "textures")
            if os.path.exists(texFolderPath):
                cls.RegisteredModPaths[mod] = texFolderPath
            else:
                raise FileNotFoundError(f"Couldn't find {texFolderPath}")
        return os.path.join(cls.RegisteredModPaths[mod], texPath)

    @classmethod
    def getXMLTexture(cls):
        texRoot = lxml.etree.Element("AllTexturesAndRegions")
        lxml.etree.SubElement(texRoot, "textures")
        lxml.etree.SubElement(texRoot, "regions")
        texTree = lxml.etree.ElementTree(texRoot)
        regionsNode = texTree.find("//regions")
        texturesNode = texTree.find("//textures")

        packedRectsSorted = {}
        for rect in cls.Packer.rect_list():
            b, x, y, w, h, regModTexIDX = rect
            regionID = cls.RegisteredTexturesCustomRegion[regModTexIDX].CoreRegionID
            packedRectsSorted[regionID] = (b, str(x), str(y), str(w), str(h), regModTexIDX)
        # NOT YET SORTED
        packedRectsSorted = {k: v for k,v in sorted(packedRectsSorted.items())}
        # NOW SORTED
        bins = set()

        for regionID, rect in packedRectsSorted.items():
            newNode = lxml.etree.SubElement(regionsNode, "re")

            rt: RegisteredTexture; rt = cls.RegisteredTexturesCustomRegion[regModTexIDX]
            regionFileName = cls.getModTexturePath(rt.ParentMod, rt.TexPath)
            bin, x, y, w, h, regModTexIDX = rect
            bins.add(bin)

            newNode.set("n", str(regionID))
            newNode.set("t", str(cls.getBinTextureID(bin)))
            newNode.set("x", x)
            newNode.set("y", y)
            newNode.set("w", w)
            newNode.set("h", h)
            newNode.set("file", regionFileName)

        for bin in bins:
            newTex = lxml.etree.SubElement(texturesNode, "t")
            newTex.set("i", str(cls.getBinTextureID(bin)))
            newTex.set("w", str(cls._TexFileResolution))
            newTex.set("h", str(cls._TexFileResolution))

        return texTree

    @classmethod
    def getBinTextureID(cls, bin: int):
        return cls.CustomTextureIDStart + bin


if __name__ == "__main__":
    """Run some basic unit tests."""
    testFileDir = "unit-tests/textures"
    for filename in os.listdir(testFileDir):
        repeat = os.stat(os.path.join(testFileDir, filename)).st_size
        # magic numbers chosen semi-randomly to get a good spread of repeats
        repeat = math.ceil((210 - repeat)/ 9) ** 2
        print(f"{filename:>11} - {repeat:>2}")
        for x in range(repeat):
            TextureManager.registerNewTexture("unit-tests", filename)

    TextureManager.pack()
    with open("unit-tests/textures-output.xml", 'wb') as f:
        f.write(lxml.etree.tostring(TextureManager.getXMLTexture(), pretty_print=True))

    for bin in TextureManager.Packer:
        r1str = f"x{bin[ 0].x}, y{bin[ 0].y} ({bin[ 0].rid})"
        r2str = f"x{bin[-1].x}, y{bin[-1].y} ({bin[-1].rid})"
        binstr = f"{len(bin):>3} rects, first {r1str}, last {r2str}"
        print(binstr)
    numBins = len(TextureManager.Packer)
    numRects = len(TextureManager.Packer.rect_list())
    numRectsRaw = len(TextureManager.RegisteredTexturesCustomRegion)
    print(f"{numBins} bins, {numRects} rects ({numRectsRaw} raw)")

    for filename in os.listdir(testFileDir):
        try:
            TextureManager.registerNewTexture("unit-tests", filename, 20)
        except KeyError as e:
            print(f"Caught KeyError as expected: {e.args[0]}")
            break

    print("CTM compiles.")
