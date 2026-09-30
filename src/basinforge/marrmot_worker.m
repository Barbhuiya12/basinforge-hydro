function marrmot_worker(source_dir, package_list, communication_dir)
% BasinForge protocol wrapper; upstream MARRMoT equations are unmodified.
% Request data are JSON/MAT, never evaluated as executable source.
  warning('off', 'Octave:shadowed-function');
  if ~isempty(package_list)
    pkg('local_list', package_list);
  end
  addpath(source_dir);
  while true
    request_file = fullfile(communication_dir, 'request.json');
    if ~exist(request_file, 'file')
      pause(0.002);
      continue;
    end
    line = fileread(request_file);
    unlink(request_file);
    try
      request = jsondecode(line);
      if strcmp(request.op, 'describe')
        files = dir(fullfile(source_dir, 'm_*.m'));
        descriptions = {};
        for i = 1:length(files)
          classname = files(i).name(1:end-2);
          if isempty(regexp(classname, '^m_[0-9][0-9]_.*_[0-9]+p_[0-9]+s$', 'once'))
            continue;
          end
          m = feval(classname);
          item = struct('class_name', classname, 'parameters', m.numParams, ...
                        'stores', m.numStores, 'bounds', m.parRanges);
          descriptions{end+1} = item;
        end
        response = struct('ok', true, 'models', {descriptions}, 'octave_version', version);
      elseif strcmp(request.op, 'run')
        classname = request.class_name;
        if isempty(regexp(classname, '^m_[0-9][0-9]_.*_[0-9]+p_[0-9]+s$', 'once')) ...
           || ~exist(fullfile(source_dir, [classname '.m']), 'file')
          error('Unrecognized MARRMoT model class.');
        end
        inputs = load(request.input_file);
        % Upstream fallback root searches use randn. Reset per simulation
        % so candidate evaluation is independent of previous requests.
        rng(0, 'twister');
        m = feval(classname);
        m.delta_t = 1;
        m.input_climate = inputs.forcing;
        m.theta = request.theta;
        m.S0 = request.s0;
        m.solver_opts = [];
        if request.details
          % Capture the upstream printed balance summary; return its value.
          evalc('[external, internal, stores, water_balance] = m.get_output();');
          q = external.Q;
          ea = external.Ea;
          residuals = m.solver_data.resnorm;
          save('-mat7-binary', request.output_file, 'q', 'ea', 'stores', 'residuals', 'water_balance');
        else
          q = m.get_streamflow();
          save('-mat7-binary', request.output_file, 'q');
        end
        response = struct('ok', true);
      else
        error('Unknown protocol operation.');
      end
    catch exception
      response = struct('ok', false, 'error', exception.message);
    end
    response_file = fullfile(communication_dir, 'response.json');
    temporary_file = [response_file '.tmp'];
    stream = fopen(temporary_file, 'w');
    fprintf(stream, '%s', jsonencode(response));
    fclose(stream);
    movefile(temporary_file, response_file);
  end
end
