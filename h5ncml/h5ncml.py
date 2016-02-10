import posixpath as pp
import urllib.request as urlrequest
import urllib.parse as urlparse
import os.path as osp
import argparse
import h5py
import numpy as np
from lxml import etree
from lxml.builder import ElementMaker


# Define XML namespaces to use...
ns = {'nc': 'http://www.unidata.ucar.edu/namespaces/netcdf/ncml-2.2',
      'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}

# A map connecting group names with their XML elements...
grp_node = dict()

# Create element factory...
E = ElementMaker(namespace=ns['nc'], nsmap=ns)
nc_group = E.group
nc_var = E.variable
nc_attr = E.attribute
nc_dim = E.dimension


def ncml_dtype(tobj):
    """Translate HDF5 datatype to NcML datatype information.

    :arg h5py.h5t.TypeID tobj: h5py.h5t.TypeID object.
    :return: A tuple with NcML datatype and a boolean flag indicating if the
        datatype is unsigned.
    :rtype: tuple
    """
    type_cls = tobj.get_class()

    unsigned = False
    ncml_type = None
    if type_cls == h5py.h5t.INTEGER:
        size = {1: 'byte',
                2: 'short',
                4: 'int',
                8: 'long'}
        if tobj.get_sign() == h5py.h5t.SGN_NONE:
            unsigned = True
        ncml_type = size[tobj.get_size()]

    elif type_cls == h5py.h5t.FLOAT:
        size = {4: 'float',
                8: 'double'}
        ncml_type = size[tobj.get_size()]

    elif type_cls == h5py.h5t.TIME:
        raise TypeError('H5T_TIME datatype not supported in NcML')

    elif type_cls == h5py.h5t.STRING:
        ncml_type = 'String'

    elif type_cls == h5py.h5t.BITFIELD:
        raise TypeError('H5T_BITFIELD datatype not supported in NcML')

    elif type_cls == h5py.h5t.OPAQUE:
        ncml_type = 'opaque'

    elif type_cls == h5py.h5t.COMPOUND:
        ncml_type = 'Structure'

    elif type_cls == h5py.h5t.REFERENCE:
        raise TypeError('H5T_REFERENCE datatype not supported in NcML')

    elif type_cls == h5py.h5t.ENUM:
        raise NotImplementedError(
            'H5T_ENUM datatype in NcML not supported yet')

    elif type_cls == h5py.h5t.VLEN:
        raise NotImplementedError(
            'H5T_VLEN datatype in NcML not supported yet')

    elif type_cls == h5py.h5t.ARRAY:
        raise TypeError('H5T_ARRAY datatype not supported in NcML')

    else:
        raise ValueError('%s: Unknown type class' % type_cls)

    return (ncml_type, unsigned)


def is_dimscale(attrs):
    """Check if a dataset is a dimension scale.

    :arg h5py.AttributeManager attrs: Dataset's attributes.
    """
    cond1 = False
    cond2 = True
    for n, v in attrs.items():
        if n == 'CLASS' and v == b'DIMENSION_SCALE':
            cond1 = True
        if n == 'REFERENCE_LIST':
            cond2 = True
    return True if cond1 and cond2 else False


def do_attributes(elem, obj):
    for aname, aval in obj.attrs.items():
        if aname in ('CLASS', 'REFERENCE_LIST', 'DIMENSION_LIST', 'NAME'):
            continue

        # Attribute's NcML datatype...
        aid = h5py.h5a.open(obj.id, aname.encode('utf-8'))
        atype, is_unsign = ncml_dtype(aid.get_type())

        # Process attribute's value...
        shape = aid.shape
        if atype == 'String':
            if len(shape) == 0:
                # Scalar attribute...
                aval = aval.decode('utf-8')
            else:
                temp = np.ravel(aval)
                aval = ' '.join([v.decode('utf-8') for v in temp])
        else:
            temp = np.ravel(aval)
            aval = ' '.join([str(v) for v in temp])

        # Create <attribute> XML element...
        axml = nc_attr({'name': aname, 'type': atype, 'value': str(aval)})
        if is_unsign:
            axml.attrib['isUnsigned'] = 'true'

        # Attach <attribute> element to its XML parent...
        elem.append(axml)


def objinfo(name, obj):
    """Callback for the HDF5 object visitor."""
    if isinstance(obj, h5py.Group):
        if obj.name in grp_node:
            raise RuntimeError('%s: XML node already exists' % obj.name)
        # elem = etree.Element(nc_group, nsmap=ns,
        #                      attrib={'name': pp.basename(obj.name)})
        elem = nc_group({'name': pp.basename(obj.name)})
        grp_node[obj.name] = elem

    elif isinstance(obj, h5py.Dataset):
        # Is the dataset a dimension scale...
        if is_dimscale(obj.attrs):
            # Create <dimension> XML element...
            elem = nc_dim({'name': pp.basename(obj.name),
                           'length': str(obj.shape[0])})
            grp_node[obj.parent.name].append(elem)

            # Is the dataset just a netCDF dimension or should also be a netCDF
            # variable...
            if obj.attrs.get('NAME', b'').startswith(
                    b'This is a netCDF dimension but not a netCDF variable.'):
                return

        # Dataset's NcML datatype...
        dset_type, is_unsign = ncml_dtype(obj.id.get_type())

        # Dataset's shape...
        if 'DIMENSION_LIST' in obj.attrs:
            f = obj.file
            shape = list()
            for n in range(len(obj.shape)):
                dim_dset = f[obj.attrs['DIMENSION_LIST'][n][0]]
                shape.append(dim_dset.name)
        else:
            shape = [str(d) for d in obj.shape]

        # Create <variable> element...
        elem = nc_var({'name': pp.basename(obj.name), 'type': dset_type,
                       'shape': ' '.join(shape)})
        if is_unsign:
            elem.append(nc_attr({'name': '_Unsigned', 'value': 'true'}))
    else:
        raise TypeError('Unexpected HDF5 object: %s' % obj)
    grp_node[obj.parent.name].append(elem)

    do_attributes(elem, obj)


def h5toncml(h5fname):
    """Generate NcML representation of HDF5 file's content.

    Dataset values not included.

    :arg str h5fname: HDF5 file name.
    :return: An instance of lxml.etree.ElementTree representing the NcML
        content.
    """
    f = h5py.File(h5fname, 'r')

    # Create the root element and the document...
    root = etree.Element(etree.QName(ns['nc'], 'netcdf'), nsmap=ns)
    ncmldoc = etree.ElementTree(root)

    # Add the XML schema attributes...
    root.attrib[etree.QName(ns['xsi'], 'schemaLocation')] = \
        'http://www.unidata.ucar.edu/schemas/netcdf/ncml-2.2.xsd'

    # Add location attribute...
    root.attrib['location'] = urlparse.urljoin(
        'file:',
        urlrequest.pathname2url(osp.abspath(h5fname)))

    # Visit each HDF5 object...
    grp_node['/'] = root
    do_attributes(root, f)
    f.visititems(objinfo)
    f.close()

    return ncmldoc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('h5f', help='HDF5 file name')
    parser.add_argument('-x', '--xpath', help='NcML XPath statement')
    args = parser.parse_args()

    if args.xpath:
        raise NotImplementedError('NcML XPath not yet supported')

    ncmldoc = h5toncml(args.h5f)

    # Spit out the file's NcML...
    print(etree.tostring(ncmldoc,
                         pretty_print=True,
                         xml_declaration=True,
                         encoding='UTF-8')
          .decode('utf-8'))
