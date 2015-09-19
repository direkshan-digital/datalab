# Copyright 2014 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Google Cloud Platform library - BigQuery IPython Functionality."""

import json
import re
import yaml
import IPython
import IPython.core.display
import IPython.core.magic
import gcp.bigquery
import gcp.data
import gcp._util
import _commands
import _html
import _utils


def _create_sample_subparser(parser):
  sample_parser = parser.subcommand('sample',
      'execute a BigQuery SQL statement and display results or create a named query object')
  sample_parser.add_argument('-q', '--sql', help='the name for this query object')
  sample_parser.add_argument('-c', '--count', type=int, default=10,
                             help='number of rows to limit to if sampling')
  sample_parser.add_argument('-m', '--method', help='the type of sampling to use',
                             choices=['limit', 'random', 'hashed', 'sorted'], default='limit')
  sample_parser.add_argument('-p', '--percent', type=int, default=1,
                             help='For random or hashed sampling, what percentage to sample from')
  sample_parser.add_argument('-f', '--field',
                             help='field to use for sorted or hashed sampling')
  sample_parser.add_argument('-o', '--order', choices=['ascending', 'descending'],
                             default='ascending', help='sort order to use for sorted sampling')
  return sample_parser


def _create_udf_subparser(parser):
  udf_parser = parser.subcommand('udf', 'create a named Javascript UDF')
  udf_parser.add_argument('-m', '--module', help='the name for this UDF', required=True)
  return udf_parser


def _create_dry_run_subparser(parser):
  dry_run_parser = parser.subcommand('dryrun',
      'Send a query to BQ in dry run mode to receive approximate usage statistics')
  dry_run_parser.add_argument('-q', '--sql',
                             help='the name of the query to be dry run', required=True)
  return dry_run_parser


def _create_execute_subparser(parser, command):
  execute_parser = parser.subcommand(command,
      'execute a BigQuery SQL statement sending results to a named table')
  execute_parser.add_argument('-nc', '--nocache', help='don\'t used previously cached results',
                              action='store_true')
  execute_parser.add_argument('-m', '--mode', help='table creation mode', default='create',
                              choices=['create', 'append', 'overwrite'])
  execute_parser.add_argument('-l', '--large', help='allow large results', action='store_true')
  execute_parser.add_argument('-q', '--sql', help='name of query to run, if not in cell body',
                              nargs='?')
  execute_parser.add_argument('-t', '--target', help='target table name', nargs='?')
  return execute_parser


def _create_pipeline_subparser(parser, command):
  pipeline_parser = parser.subcommand(command,
                                      'define a deployable pipeline based on a BigQuery SQL query')
  pipeline_parser.add_argument('-n', '--name', help='pipeline name')
  pipeline_parser.add_argument('-nc', '--nocache', help='don\'t used previously cached results',
                               action='store_true')
  pipeline_parser.add_argument('-m', '--mode', help='table creation mode', default='create',
                               choices=['create', 'append', 'overwrite'])
  pipeline_parser.add_argument('-l', '--large', help='allow large results', action='store_true')
  pipeline_parser.add_argument('-q', '--sql', help='name of query to run', required=True)
  pipeline_parser.add_argument('-t', '--target', help='target table name', nargs='?')
  pipeline_parser.add_argument('action', nargs='?', choices=('deploy', 'run', 'dryrun'),
                               default='dryrun',
                               help='whether to deploy the pipeline, execute it immediately in ' +
                                    'the notebook, or validate it with a dry run')
  # TODO(gram): we may want to move some command line arguments to the cell body config spec
  # eventually.
  return pipeline_parser


def _create_table_subparser(parser):
  table_parser = parser.subcommand('table', 'view a BigQuery table')
  table_parser.add_argument('-r', '--rows', type=int, default=25,
                            help='rows to display per page')
  table_parser.add_argument('-c', '--cols',
                            help='comma-separated list of column names to restrict to')
  return table_parser


def _create_schema_subparser(parser):
  schema_parser = parser.subcommand('schema', 'view a BigQuery table or view schema')
  schema_parser.add_argument('item', help='the name of, or a reference to, the table or view')
  return schema_parser


def _create_datasets_subparser(parser):
  datasets_parser = parser.subcommand('datasets', 'list the datasets in a BigQuery project')
  datasets_parser.add_argument('-p', '--project',
                               help='the project whose datasets should be listed')
  return datasets_parser


def _create_tables_subparser(parser):
  tables_parser = parser.subcommand('tables', 'list the tables in a BigQuery project or dataset')
  tables_parser.add_argument('-p', '--project',
                             help='the project whose tables should be listed')
  tables_parser.add_argument('-d', '--dataset',
                             help='the dataset to restrict to')
  return tables_parser


def _create_extract_subparser(parser):
  extract_parser = parser.subcommand('extract', 'Extract BigQuery query results or table to GCS')
  extract_parser.add_argument('source', help='the query or table to extract')
  extract_parser.add_argument('-f', '--format', choices=['csv', 'json'], default='csv',
                              help='format to use for the export')
  extract_parser.add_argument('-c', '--compress', action='store_true', help='compress the data')
  extract_parser.add_argument('-H', '--header', action='store_true', help='include a header line')
  extract_parser.add_argument('-d', '--delimiter', default=',', help='field delimiter')
  extract_parser.add_argument('destination', help='the URL of the destination')
  return extract_parser


def _create_load_subparser(parser):
  load_parser = parser.subcommand('load', 'load data into a BigQuery table')
  load_parser.add_argument('-m', '--mode', help='one of create (default), append or overwrite',
                           choices=['create', 'append', 'overwrite'], default='create')
  load_parser.add_argument('-f', '--format', help='source format', choices=['json', 'csv'],
                           default='csv')
  load_parser.add_argument('-n', '--skip', help='number of initial lines to skip',
                           type=int, default=0)
  load_parser.add_argument('-s', '--strict', help='reject bad values and jagged lines',
                           action='store_true')
  load_parser.add_argument('-d', '--delimiter', default=',',
                           help='the inter-field delimiter (default ,)')
  load_parser.add_argument('-q', '--quote', default='"',
                           help='the quoted field delimiter (default ")')
  load_parser.add_argument('-i', '--infer', help='attempt to infer schema from source',
                           action='store_true')
  load_parser.add_argument('source', help='URL of the GCS source(s)')
  load_parser.add_argument('table', help='the destination table')
  return load_parser


def _create_bigquery_parser():
  """ Create the parser for the %bigquery magics.

  Note that because we use the func default handler dispatch mechanism of argparse,
  our handlers can take only one argument which is the parsed args. So we must create closures
  for the handlers that bind the cell contents and thus must recreate this parser for each
  cell upon execution.
  """
  parser = _commands.CommandParser.create('bigquery')

  # This is a bit kludgy because we want to handle some line magics and some cell magics
  # with the bigquery command.

  # %%bigquery sample
  sample_parser = _create_sample_subparser(parser)
  sample_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell, sample_parser, _sample_cell))

  # %%bigquery dryrun
  dryrun_parser = _create_dry_run_subparser(parser)
  dryrun_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell, dryrun_parser,
                                                _dryrun_cell, cell_prohibited=True))

  # %%bigquery udf
  udf_parser = _create_udf_subparser(parser)
  udf_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell, udf_parser,
                                                _udf_cell, cell_required=True))

  # %%bigquery execute
  execute_parser = _create_execute_subparser(parser, 'execute')
  execute_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell,
                                                execute_parser, _execute_cell))

  # %%bigquery pipeline
  pipeline_parser = _create_pipeline_subparser(parser, 'pipeline')

  pipeline_parser.set_defaults(
    func=lambda args, cell: _dispatch_handler(args, cell,
                                              pipeline_parser, _pipeline_cell))

  # %bigquery table
  table_parser = _create_table_subparser(parser)
  table_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell, table_parser,
                                                _table_line, cell_prohibited=True))

  # %bigquery schema
  schema_parser = _create_schema_subparser(parser)
  schema_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell,
                                                schema_parser, _schema_line, cell_prohibited=True))

  # %bigquery datasets
  datasets_parser = _create_datasets_subparser(parser)
  datasets_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell, datasets_parser,
                                                _datasets_line, cell_prohibited=True))

  # %bigquery tables
  tables_parser = _create_tables_subparser(parser)
  tables_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell, tables_parser,
                                                _tables_line, cell_prohibited=True))

  # % bigquery extract
  extract_parser = _create_extract_subparser(parser)
  extract_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell, extract_parser,
                                                _extract_line, cell_prohibited=True))

  # %bigquery load
  # TODO(gram): need some additional help, esp. around the option of specifying schema in
  # cell body and how schema infer may fail.
  load_parser = _create_load_subparser(parser)
  load_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell, load_parser, _load_cell))
  return parser


_bigquery_parser = _create_bigquery_parser()


@IPython.core.magic.register_line_cell_magic
def bigquery(line, cell=None):
  """Implements the bigquery cell magic for ipython notebooks.

  The supported syntax is:

    %%bigquery <command> [<args>]
    <cell>

  or:

    %bigquery <command> [<args>]

  Use %bigquery --help for a list of commands, or %bigquery <command> --help for help
  on a specific command.
  """
  namespace = {}
  if line.find('$') >= 0:
    # We likely have variables to expand; get the appropriate context.
    namespace = _notebook_environment()

  return _utils.handle_magic_line(line, cell, _bigquery_parser, namespace=namespace)


def _dispatch_handler(args, cell, parser, handler,
                      cell_required=False, cell_prohibited=False):
  """ Makes sure cell magics include cell and line magics don't, before dispatching to handler.

  Args:
    args: the parsed arguments from the magic line.
    cell: the contents of the cell, if any.
    parser: the argument parser for <cmd>; used for error message.
    handler: the handler to call if the cell present/absent check passes.
    cell_required: True for cell magics, False for line magics that can't be cell magics.
    cell_prohibited: True for line magics, False for cell magics that can't be line magics.
  Returns:
    The result of calling the handler.
  Raises:
    Exception if the invocation is not valid.
  """
  if cell_prohibited:
    if cell and len(cell.strip()):
      parser.print_help()
      raise Exception('Additional data is not supported with the %s command.' % parser.prog)
    return handler(args)

  if cell_required and not cell:
    parser.print_help()
    raise Exception('The %s command requires additional data' % parser.prog)

  return handler(args, cell)


def _parse_config(config, env):
  """ Parse a config from a magic cell body. This could be JSON or YAML. We turn it into
      a Python dictionary then recursively replace any variable references.
  """
  def expand_var(v, env):
    if v.startswith('$'):
      v = v[1:]
      if not v.startwith('$'):
        if v in env:
          v = env[v]
        else:
          raise Exception('Cannot expand variable $%s' % v)
    return v

  def replace_vars(config, env):
    if isinstance(config, dict):
      for k, v in config.items():
        if isinstance(v, dict) or isinstance(v, list) or isinstance(v, tuple):
          replace_vars(v, env)
        elif isinstance(v, basestring):
          config[k] = expand_var(v, env)
    elif isinstance(config, list) or isinstance(config, tuple):
      for i, v in enumerate(config):
        if isinstance(v, dict) or isinstance(v, list) or isinstance(v, tuple):
          replace_vars(v, env)
        elif isinstance(v, basestring):
          config[i] = expand_var(v, env)

  if config is None:
    return None
  stripped = config.strip()
  if len(stripped) == 0:
    config = {}
  elif stripped[0] == '{':
    config = json.loads(config)
  else:
    config = yaml.load(config)

  # Now we need to walk the config dictionary recursively replacing any '$name' vars.

  replace_vars(config, env)
  return config


def _get_query_argument(args, config, env):
  """ Get a query argument to a cell magic.

  The query is specified with args['sql']. We look that up and if it is a BQ query
  just return it. If it is instead a SqlModule or SqlStatement it may have variable
  references. We resolve those using the arg parser for the SqlModule, then override
  the resulting defaults with either the Python code in code, or the dictionary in
  overrides. The latter is for if the overrides are specified with YAML or JSON and
  eventually we should eliminate code in favor of this.
  """
  sql_arg = args['sql']
  item = _get_notebook_item(sql_arg)
  if isinstance(item, gcp.bigquery.Query):
    return item

  item, env = gcp.data.SqlModule.get_sql_statement_with_environment(item, env)
  if config:
    env.update(config)
  return gcp.bigquery.Query(item, **env)


def _sample_cell(args, config):
  """Implements the bigquery sample cell magic for ipython notebooks.

  Args:
    args: the optional arguments following '%%bigquery sample'.
    config: optional contents of the cell interpreted as YAML or JSON.
  Returns:
    The results of executing the query converted to a dataframe if no variable
    was specified. None otherwise.
  """

  env = _notebook_environment()
  config = _parse_config(config, env)
  query = _get_query_argument(args, config, env)

  count = args['count']
  method = args['method']
  if method == 'random':
    sampling = gcp.bigquery.Sampling.random(percent=args['percent'], count=count)
  elif method == 'hashed':
    sampling = gcp.bigquery.Sampling.hashed(field_name=args['field'],
                                            percent=args['percent'],
                                            count=count)
  elif method == 'sorted':
    ascending = args['order'] == 'ascending'
    sampling = gcp.bigquery.Sampling.sorted(args['field'],
                                            ascending=ascending,
                                            count=count)
  elif method == 'limit':
    sampling = gcp.bigquery.Sampling.default(count=count)
  else:
    sampling = gcp.bigquery.Sampling.default(count=count)

  return query.sample(sampling=sampling)


def _dryrun_cell(args, config):
  """Implements the BigQuery cell magic used to dry run BQ queries.

   The supported syntax is:
   %%bigquery dryrun -q|--sql <query identifier>
   <config>

  Args:
    args: the argument following '%bigquery dryrun'.
    config: optional contents of the cell interpreted as YAML or JSON.
  Returns:
    The response wrapped in a DryRunStats object
  """
  env = _notebook_environment()
  config = _parse_config(config, env)
  query = _get_query_argument(args, config, env)

  result = query.execute_dry_run()
  return gcp.bigquery._query_stats.QueryStats(total_bytes=result['totalBytesProcessed'],
                                              is_cached=result['cacheHit'])


def _udf_cell(args, js):
  """Implements the bigquery_udf cell magic for ipython notebooks.

  The supported syntax is:
  %%bigquery udf --module <var>
  <js function>

  Args:
    args: the optional arguments following '%%bigquery udf'.
    declaration: the variable to initialize with the resulting UDF object.
    js: the UDF declaration (inputs and outputs) and implementation in javascript.
  Returns:
    The results of executing the UDF converted to a dataframe if no variable
    was specified. None otherwise.
  """
  variable_name = args['module']
  if not variable_name:
    raise Exception("Declaration must be of the form %%bigquery udf --module <variable name>")

  # Parse out the input and output specification
  spec_pattern = r'\{\{([^}]+)\}\}'
  spec_part_pattern = r'[a-z_][a-z0-9_]*'

  specs = re.findall(spec_pattern, js)
  if len(specs) < 2:
    raise Exception('The JavaScript must declare the input row and output emitter parameters '
                    'using valid jsdoc format comments.\n'
                    'The input row param declaration must be typed as {{field:type, field2:type}} '
                    'and the output emitter param declaration must be typed as '
                    'function({{field:type, field2:type}}.')

  inputs = []
  input_spec_parts = re.findall(spec_part_pattern, specs[0], flags=re.IGNORECASE)
  if len(input_spec_parts) % 2 != 0:
    raise Exception('Invalid input row param declaration. The jsdoc type expression must '
                    'define an object with field and type pairs.')
  for n, t in zip(input_spec_parts[0::2], input_spec_parts[1::2]):
    inputs.append((n, t))

  outputs = []
  output_spec_parts = re.findall(spec_part_pattern, specs[1], flags=re.IGNORECASE)
  if len(output_spec_parts) % 2 != 0:
    raise Exception('Invalid output emitter param declaration. The jsdoc type expression must '
                    'define a function accepting an an object with field and type pairs.')
  for n, t in zip(output_spec_parts[0::2], output_spec_parts[1::2]):
    outputs.append((n, t))

  # Finally build the UDF object
  udf = gcp.bigquery.UDF(inputs, outputs, variable_name, js)
  _notebook_environment()[variable_name] = udf


def _execute_cell(args, config):
  """Implements the BigQuery cell magic used to execute BQ queries.

   The supported syntax is:
   %%bigquery execute -q|--sql <query identifier> <other args>
   <config>

  Args:
    args: the arguments following '%bigquery execute'.
    config: optional contents of the cell interpreted as YAML or JSON.
  Returns:
    The QueryResultsTable
  """
  env = _notebook_environment()
  config = _parse_config(config, env)
  query = _get_query_argument(args, config, env)
  return query.execute(args['target'], table_mode=args['mode'], use_cache=not args['nocache'],
                       allow_large_results=args['large']).results


def _pipeline_cell(args, config):
  """Implements the BigQuery cell magic used to validate, execute or deploy BQ pipelines.

   The supported syntax is:
   %%bigquery pipeline -q|--sql <query identifier> <other args> <action>
   <config>

  Args:
    args: the arguments following '%bigquery pipeline'.
    config: optional contents of the cell interpreted as YAML or JSON.
  Returns:
    The QueryResultsTable
  """
  if args['action'] == 'deploy':
    return 'Deploying a pipeline is not yet supported'

  env = {}
  for key, value in _notebook_environment().iteritems():
    if isinstance(value, gcp.bigquery._udf.FunctionCall):
      env[key] = value

  config = _parse_config(config, env)
  query = _get_query_argument(args, config, env)
  if args['action'] == 'dryrun':
    print(query.sql)
    result = query.execute_dry_run()
    return gcp.bigquery._query_stats.QueryStats(total_bytes=result['totalBytesProcessed'],
                                                is_cached=result['cacheHit'])
  if args['action'] == 'run':
    return query.execute(args['target'], table_mode=args['mode'], use_cache=not args['nocache'],
                         allow_large_results=args['large']).results


def _table_line(args):
  name = args['table']
  table = _get_table(name)
  if table and table.exists():
    fields = args['cols'].split(',') if args['cols'] else None
    html = _table_viewer(table, rows_per_page=args['rows'], fields=fields)
    return IPython.core.display.HTML(html)
  else:
    return "%s does not exist" % name


def _notebook_environment():
  ipy = IPython.get_ipython()
  return ipy.user_ns


def _get_notebook_item(name):
  """ Get an item from the IPython environment. """
  env = _notebook_environment()
  return gcp._util.get_item(env, name)


def _get_schema(name):
  """ Given a variable or table name, get the Schema if it exists. """
  item = _get_notebook_item(name)
  if not item:
    item = _get_table(name)

  if isinstance(item, gcp.bigquery.Schema):
    return item
  if hasattr(item, 'schema') and isinstance(item.schema, gcp.bigquery._schema.Schema):
    return item.schema
  return None


# An LRU cache for Tables. This is mostly useful so that when we cross page boundaries
# when paging through a table we don't have to re-fetch the schema.
_table_cache = gcp._util.LRUCache(10)


def _get_table(name):
  """ Given a variable or table name, get a Table if it exists.

  Args:
    name: the name of the Table or a variable referencing the Table.
  Returns:
    The Table, if found.
  """
  # If name is a variable referencing a table, use that.
  item = _get_notebook_item(name)
  if isinstance(item, gcp.bigquery.Table):
    return item
  # Else treat this as a BQ table name and return the (cached) table if it exists.
  try:
    return _table_cache[name]
  except KeyError:
    table = gcp.bigquery.Table(name)
    if table.exists():
      _table_cache[name] = table
      return table
  return None


def _schema_line(args):
  name = args['item']
  schema = _get_schema(name)
  if schema:
    html = _repr_html_table_schema(schema)
    return IPython.core.display.HTML(html)
  else:
    return "%s does not exist" % name


def _render_table(data, fields=None):
  """ Helper to render a list of dictionaries as an HTML display object. """
  return IPython.core.display.HTML(_html.HtmlBuilder.render_table(data, fields))


def _datasets_line(args):
  return _render_table([{'Name': str(dataset)}
                        for dataset in gcp.bigquery.DataSets(args['project'])])


def _tables_line(args):
  if args['dataset']:
    datasets = [gcp.bigquery.DataSet((args['project'], args['dataset']))]
  else:
    datasets = gcp.bigquery.DataSets(args['project'])

  tables = []
  for dataset in datasets:
    tables.extend([{'Name': str(table)} for table in dataset])

  return _render_table(tables)


def _extract_line(args):
  name = args['source']
  source = _get_notebook_item(name)
  if not source:
    source = _get_table(name)

  if not source:
    return 'No such source: %s' % name
  elif isinstance(source, gcp.bigquery.Table) and not source.exists():
    return 'Source %s does not exist' % name
  else:

    job = source.extract(args['destination'],
                         format='CSV' if args['format'] == 'csv' else 'NEWLINE_DELIMITED_JSON',
                         compress=args['compress'],
                         csv_delimiter=args['delimiter'],
                         csv_header=args['header'])
    if job.failed:
      return 'Extract failed: %s' % str(job.fatal_error)
    elif job.errors:
      return 'Extract completed with errors: %s' % str(job.errors)


def _load_cell(args, schema):
  name = args['table']
  table = _get_table(name)
  if not table:
    table = gcp.bigquery.Table(name)

  if table.exists():
    if args['mode'] == 'create':
      return "%s already exists; use --append or --overwrite" % name
  elif schema:
    table.create(json.loads(schema))
  elif not args['infer']:
    return 'Table does not exist, no schema specified in cell and no --infer flag; cannot load'

  # TODO(gram): we should probably try do the schema infer ourselves as BQ doesn't really seem
  # to be able to do it. Alternatively we can drop the --infer argument and force the user
  # to use a pre-existing table or supply a JSON schema.
  job = table.load(args['source'],
                   mode=args['mode'],
                   source_format=('CSV' if args['format'] == 'csv' else 'NEWLINE_DELIMITED_JSON'),
                   csv_delimiter=args['delimiter'],
                   csv_skip_header_rows=args['skip'],
                   allow_jagged_rows=not args['strict'],
                   ignore_unknown_values=not args['strict'],
                   quote=args['quote'])
  if job.failed:
    return 'Load failed: %s' % str(job.fatal_error)
  elif job.errors:
    return 'Load completed with errors: %s' % str(job.errors)


def _table_viewer(table, rows_per_page=25, fields=None):
  """  Return a table viewer.

  Args:
    table: the table to view.
    rows_per_page: how many rows to display at one time.
    fields: an array of field names to display; default is None which uses the full schema.
  Returns:
    A string containing the HTML for the table viewer.
  """
  if not table.exists():
    return "%s does not exist" % str(table)

  _HTML_TEMPLATE = """
    <div class="bqtv" id="%s"></div>
    <div><br />%s %s<br />%s</div>
    <script>
      require(['extensions/charting', 'element!%s'%s],
        function(charts, dom) {
          charts.render(dom,
            {
              chartStyle:"%s",
              dataName:"%s",
              fields:"%s",
              totalRows:%d,
              rowsPerPage:%d,
            }, {}, %s);
        }
      );
    </script>
  """

  if fields is None:
    fields = _utils.get_field_list(fields, table.schema)
  div_id = _html.Html.next_id()
  meta_count = ("rows: %d" % table.length) if table.length >= 0 else ''
  meta_name = str(table) if table.job is None else table.job.id
  meta_data = ''
  if table.job:
    if table.job.cache_hit:
      data_cost = 'cached'
    else:
      bytes = gcp.bigquery._query_stats.QueryStats._size_formatter(table.job.bytes_processed)
      data_cost = '%s processed' % bytes
    meta_data = '(%.1fs, %s)' % (table.job.total_time, data_cost)
  data, total_count = _utils.get_data(table, fields, 0, rows_per_page)

  if total_count < 0:
    # The table doesn't have a length metadata property but may still be small if we fetched less
    # rows than we asked for.
    fetched_count = len(data['rows'])
    if fetched_count < rows_per_page:
      total_count = fetched_count

  chart = 'table' if 0 <= total_count <= rows_per_page else 'paged_table'

  return _HTML_TEMPLATE %\
      (div_id, meta_name, meta_data, meta_count, div_id, _html.Html.get_style_arg('charting.css'),
       chart, str(table), ','.join(fields), total_count, rows_per_page,
       json.dumps(data, cls=gcp._util.JSONEncoder))


def _repr_html_query(query):
  # TODO(nikhilko): Pretty print the SQL
  return _html.HtmlBuilder.render_text(query.sql, preformatted=True)


def _repr_html_query_results_table(results):
  return _table_viewer(results)


def _repr_html_table(results):
  return _table_viewer(results)


def _repr_html_table_schema(schema):
  _HTML_TEMPLATE = """
    <div class="bqsv" id="%s"></div>
    <script>
      require(['extensions/bigquery', 'element!%s'%s],
          function(bq, dom) {
              bq.renderSchema(dom, %s);
          }
      );
    </script>
    """
  id = _html.Html.next_id()
  return _HTML_TEMPLATE % (id, id, _html.Html.get_style_arg('bigquery.css'),
                           json.dumps(schema._bq_schema))


def _repr_html_function_evaluation(evaluation):
  _HTML_TEMPLATE = """
    <div class="bqtv" id="%s"></div>
    <script>
      require(['extensions/bigquery', 'element!%s'],
          function(bq, dom) {
              bq.evaluateUDF(dom, %s, %s);
          }
      );
    </script>
    """
  id = _html.Html.next_id()
  return _HTML_TEMPLATE % (id, id, evaluation.implementation, json.dumps(evaluation.data))


def _register_html_formatters():
  try:
    ipy = IPython.get_ipython()
    html_formatter = ipy.display_formatter.formatters['text/html']

    html_formatter.for_type_by_name('gcp.bigquery._query', 'Query', _repr_html_query)
    html_formatter.for_type_by_name('gcp.bigquery._query_results_table', 'QueryResultsTable',
                                    _repr_html_query_results_table)
    html_formatter.for_type_by_name('gcp.bigquery._table', 'Table', _repr_html_table)
    html_formatter.for_type_by_name('gcp.bigquery._schema', 'Schema', _repr_html_table_schema)
    html_formatter.for_type_by_name('gcp.bigquery._udf', 'FunctionEvaluation',
                                    _repr_html_function_evaluation)
  except TypeError:
    # For when running unit tests
    pass

_register_html_formatters()
