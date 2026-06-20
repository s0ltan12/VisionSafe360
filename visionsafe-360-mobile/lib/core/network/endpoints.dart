class Endpoints {
  const Endpoints._();

  static const login = '/auth/login';
  static const profile = '/auth/profile';
  static const incidents = '/incidents';
  static String incidentById(String id) => '/incidents/$id';
  static String acknowledgeIncident(String id) => '/incidents/$id/acknowledge';
  static String resolveIncident(String id) => '/incidents/$id/resolve';
  static const history = '/incidents/history';
}
