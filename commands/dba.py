import os
import click
import yaml
import json
import csv
import webapp.api as API
from sqlalchemy.inspection import inspect
from flask.cli import with_appcontext
from flask.cli import AppGroup
from webapp.commands.schema import ( listSchemas,
                                     getCurrentVersion,
                                     getCurrentSchema,
                                     copySchema,
                                     listTables )

@click.group( cls = AppGroup )
def dba():
    """DBA backup / restore for the webapp application."""


@dba.command( 'backup', short_help = 'Backup the database.' )
@click.option( '--list/--nolist', '_list', default = False, help = 'List the schemes' )
@click.option( '--name', nargs=1, type=str )
@click.option( '--schema', nargs=1, type=str )
@with_appcontext
def backup( _list, name, schema ):
    if _list:
        print( "Available schemas like {}".format( getCurrentSchema() ) )
        for sch in listSchemas():
            print( "> {}".format( sch ) )

        return

    API.app.logger.info( "DBA backup name: {} schema: {}".format( name, schema ) )
    oSchema = getCurrentSchema()
    if name is None:
        # Create schema based on the alembic version
        # If it exists drop the schema first
        if schema is None:
            # Backup within the current schema
            schema = '{}_{}'.format( oSchema, getCurrentVersion() )

    else:
        # Create schema based on the name
        # If it exists drop the schema first
        if schema is None:
            schema = '{}_{}'.format( oSchema, name )

        else:
            schema = '{}_{}'.format( schema, name )

    API.app.logger.info( "Copy '{}' to '{}'".format( oSchema, schema ) )
    copySchema( oSchema, schema )
    return


@dba.command( 'restore', short_help = 'Restore the database.' )
@click.option( '--list/--nolist', '_list', default = False, help = 'List the schemes' )
@click.option( '--name', nargs=1, type=str )
@click.option( '--schema', nargs=1, type=str )
@with_appcontext
def restore( _list, name, schema ):
    if _list:
        print( "Available schemas like {}".format( getCurrentSchema() ) )
        for sch in listSchemas():
            print( "> {}".format( sch ) )

        return

    API.app.logger.info( "DBA restore name: {} schema: {}".format( name, schema ) )
    nSchema = getCurrentSchema()
    if name is None:
        if schema is None:
            schema = '{}_{}'.format( nSchema, getCurrentVersion() )

    else:
        if schema is None:
            schema = '{}_{}'.format( nSchema, name )

        else:
            schema = '{}_{}'.format( schema, name )

        if schema not in listSchemas():
            API.app.logger.error( "Need to supply a existing name" )
            restore( True, None )
            return

    print( "Copy '{}' to '{}'".format( schema, nSchema ) )
    copySchema( schema, nSchema )
    return


@dba.command( 'export', short_help = 'Export the database.' )
@click.option( '--fmt',
               nargs = 1,
               default = "yaml",
               help = "file export format",
               type = click.Choice( [ 'yaml', 'json', 'sql', 'csv' ], case_sensitive = False ) )
@click.option( '--table',
               nargs = 1,
               default = None,
               help = "export one table" )
@click.argument( 'filename' )
def export( fmt, filename, table ):
    # print( "Format: {}".format( fmt ))
    if fmt == 'csv':
        if filename.endswith( fmt ):
            filename = filename.split( '.' )[ 0 ]

        for tbl in listTables():
            if table is not None and table != tbl:
                continue

            model = API.db.get_model_by_tablename( tbl )
            if model is None:
                continue

            API.app.logger.info( "Table: {}".format( tbl ) )
            records = API.db.session.query( model ).all()
            if len( records ) > 0:
                filename = "{}-{}.{}".format( filename, tbl, fmt )
                API.app.logger.info( "Output filename: {}".format( filename ) )
                with open( filename, 'w' ) as stream:
                    csvwriter = csv.writer( stream, delimiter = ';', quotechar = '"' )

                    csvwriter.writerow( records[ 0 ].toDict().keys() )
                    for record in records:
                        csvwriter.writerow( record.toDict().values() )

                API.app.logger.info( "No of records: {}".format( len( records ) ) )

            else:
                API.app.logger.warning( "Nothing to export" )

    else:
        if not filename.endswith( fmt ):
            filename += ".{}".format( fmt )

        API.app.logger.info( "Output filename: {}".format( filename ) )
        with open( filename, 'w' ) as stream:
            from sqlalchemy import Table
            # create dict per record ans save:
            blob = []
            for tbl in listTables():
                if table is not None and table != tbl:
                    continue

                model = API.db.get_model_by_tablename( tbl )
                if model is None:
                    continue

                API.app.logger.info( "Table: {}".format( tbl ) )
                records = API.db.session.query( model ).all()
                if 'sql' == fmt:
                    stream.write( "-- TABLE {}\n".format( tbl ) )
                    for record in records:
                        stream.write( "{}\n".format( record.toSql() ) )

                    API.app.logger.info( "No of records: {}".format( len( records ) ) )

                else:
                    blob.append( { 'table': tbl,
                                   'records': [ rec.toDict() for rec in records ] } )

                    API.app.logger.info( "No of records: {}".format( len( records ) ) )

            if fmt == 'yaml':
                yaml.dump( blob, stream, default_style = False, default_flow_style = False )

            elif fmt == 'json':
                json.dump( blob, stream, indent = 4 )

    return


@dba.command( 'inport', short_help = 'Inport the database.' )
@click.option( '--fmt',
               nargs = 1,
               default = "yaml",
               help = "file inport format",
               type = click.Choice( [ 'yaml', 'json', 'sql', 'csv' ], case_sensitive = False ) )
@click.option( '--table',
               nargs = 1,
               default = None,
               help = "export one table" )
@click.argument( 'filename' )
def inport( fmt, filename, table ):
    if fmt in ( 'sql', 'yaml', 'json' ):
        if not filename.endswith( fmt ):
            filename += ".{}".format( fmt )

        if not os.path.isfile( filename ):
            API.app.logger.error( "Filename {} doesn't exists".format( filename ) )
            return

    if fmt == 'csv':
        if filename.endswith( fmt ):
            filename = filename.split( '.' )[ 0 ]

        if table is None and '-' in filename:
            name, table = filename.split( '-', 1 )

        else:
            name = filename

        for tbl in listTables():
            if table is not None and table != tbl:
                continue

            model = API.db.get_model_by_tablename( tbl )
            if model is None:
                continue

            filename = "{}-{}.{}".format( name, tbl, fmt )
            API.app.logger.info( "Input filename: {}".format( filename ) )
            if not os.path.isfile( filename ):
                API.app.logger.error( "Filename must be formatted as input filename {} doesn't exists".format( filename ) )
                continue

            with open( filename, 'r' ) as stream:
                csvreader = csv.reader( stream, delimiter = ';', quotechar = '"', quoting = csv.QUOTE_MINIMAL )
                it = iter( csvreader )
                header = it.__next__()
                for row in it:
                    obj = model()
                    for field, value in zip( header, row ):
                        setattr( obj, field, value )

                    API.db.session.add( obj )

                API.db.session.commit()

    else:
        with open( filename, 'r' ) as stream:
            blob = None
            if fmt == 'json':
                blob = json.load( stream )

            elif fmt == 'yaml':
                blob = yaml.load( stream )

            else: # sql
                connection = API.db.session.connection()
                for line in stream.readlines():
                    if line.startswith( '--' ):
                        continue

                    try:
                        line = line.replace( '\n', '' )
                        print( line )
                        result = connection.execute( line )
                        if result.rowcount != 1:
                            raise Exception( "row not inserted" )


                    except Exception as exc:
                        API.app.logger.error( exc )

                API.db.session.commit()

            if blob:
                # Handle the yaml/json data
                for table_data in blob:
                    records = table_data[ 'records' ]
                    if len( records ) >  0:
                        model = API.db.get_model_by_tablename( table_data[ 'table' ] )
                        if model is None:
                            continue

                        for record in records:
                            obj = model()
                            for field, value in record.items():
                                setattr( obj, field, value )

                            API.db.session.add( obj )
                            API.db.session.commit()

    return


def resolve_fieldname( settings, table, field ):
    prefixes = settings.get( 'prefixes', {} )
    field = "{}{}".format( prefixes.get( table, '' ), field )
    options = settings.get( 'options', {} )
    field_opr = options.get( 'fieldname', None )
    if field_opr is not None:
        field_opr = getattr( field, field_opr )
        field = field_opr()

    return field


def getReference( settings, table, field, value ):
    ref_model = API.db.get_model_by_tablename( table )
    query = API.db.session.query( ref_model )
    if isinstance( field, ( list, tuple ) ):
        for fld, val in zip( field, value ):
            fld = resolve_fieldname(settings, table, fld )
            query = query.filter( getattr( ref_model, fld ) == val )

    else:
        field = resolve_fieldname(settings, table, field)
        query = query.filter( getattr( ref_model, field ) == value )

    return query.one()


@dba.command( 'loader',
              short_help = 'Load the database.' )
@click.option( '--fmt',
               nargs = 1,
               default = "yaml",
               help = "file inport format",
               type = click.Choice( [ 'yaml', 'json' ],
                                    case_sensitive = False ) )
@click.argument( 'filename' )
def loader( fmt, filename ):
    settings = {}
    if not filename.endswith( fmt ):
        filename = "{}.{}".format( filename, fmt )

    if not os.path.isfile( filename ):
        print( "File doesn't exists" )
        return

    with open( filename,'r' ) as stream:
        data = yaml.load( stream )

    if '__settings__' in data:
        settings = data[ '__settings__' ]

    for table, values in data.items():
        if table.startswith( '__' ):
            continue

        model = API.db.get_model_by_tablename( table )
        if model is  None:
            continue

        for table_data in values:
            updateRecord( settings, model, table, table_data )

    return

def updateRecord( settings, model, table, table_data ):
    record = model()
    for field, value in table_data.items():
        if isinstance( value, ( bool, int, str, float ) ):
            field = resolve_fieldname( settings, table, field )
            print( "Field: {}.{} with value {}".format( table, field, value ) )
            setattr( record, field, value )

        elif isinstance( value, ( tuple, list ) ):
            field = resolve_fieldname( settings, table, field )
            ref_record = getReference( settings, *value )
            setattr( record, field, inspect( ref_record ).identity[0] )
            print("Field: {}.{} with value {}".format(table, field, inspect( ref_record ).identity[0] ) )

        elif isinstance( value, dict ):
            field = resolve_fieldname( settings, table, field )
            ref_field = value.get('field', None )
            if ref_field is None:
                fields = value.get('fields')
                if fields is None:
                    raise Exception( "missing field or fields" )

                ref_model = API.db.get_model_by_tablename( value.get( 'table' ) )
                if ref_model is None:
                    continue

                ref_record = updateRecord( settings, ref_model, value.get( 'table' ), fields )

            else:
                ref_record = getReference( settings,
                                       value.get( 'table' ),
                                       value.get( 'field' ),
                                       value.get( 'value' ) )

            setattr( record, field, inspect( ref_record ).identity[0] )
            print("Field: {}.{} with value {}".format(table, field, inspect( ref_record ).identity[0] ) )

    API.db.session.add( record )
    API.db.session.commit()
    return record


@dba.command( 'reader',
              short_help = 'Load the database.' )
@click.option( '--fmt',
               nargs = 1,
               default = "yaml",
               help = "file inport format",
               type = click.Choice( [ 'yaml', 'json' ],
                                    case_sensitive = False ) )
@click.argument( 'table' )
@click.argument( 'filename' )
def loader( fmt, table, filename ):



    return
