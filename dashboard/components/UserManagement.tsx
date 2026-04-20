
import React, { useState, useEffect, useCallback } from 'react';
import { Plus, MoreVertical, Shield, User as UserIcon, X, CheckCircle2, Trash2, Edit2 } from 'lucide-react';
import { User, UserRole } from '../types';
import { useLanguage } from '../contexts/LanguageContext';
import { UsersAPI } from '../api';



const UserManagement = () => {
  const { t } = useLanguage();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);

  const fetchUsers = useCallback(async () => {
    try {
      setLoading(true);
      const data = await UsersAPI.getAll();
      setUsers(data);
    } catch (error) {
      console.error('Failed to fetch users:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  // Form state
  const [formName, setFormName] = useState('');
  const [formEmail, setFormEmail] = useState('');
  const [formRole, setFormRole] = useState<UserRole>('Safety Engineer');

  const resetForm = () => {
    setFormName('');
    setFormEmail('');
    setFormRole('Safety Engineer');
    setEditingUser(null);
  };

  const handleOpenAddModal = () => {
    resetForm();
    setShowAddModal(true);
  };

  const handleOpenEditModal = (user: User) => {
    setFormName(user.name);
    setFormEmail(user.email);
    setFormRole(user.role);
    setEditingUser(user);
    setShowAddModal(true);
  };

  const handleSaveUser = async () => {
    if (!formName.trim() || !formEmail.trim()) return;

    try {
      if (editingUser) {
        const updated = await UsersAPI.update(editingUser.id, { name: formName, email: formEmail, role: formRole });
        setUsers(prev => prev.map(u => u.id === editingUser.id ? updated : u));
      } else {
        const newUser: User = {
          id: String(Date.now()),
          name: formName,
          email: formEmail,
          role: formRole,
          status: 'Active',
        };
        const created = await UsersAPI.create(newUser);
        setUsers(prev => [...prev, created]);
      }
      setShowAddModal(false);
      resetForm();
    } catch (e) {
      console.error('Failed to save user:', e);
      // Optional: alert the user here
    }
  };

  const handleDeleteUser = async (id: string) => {
    if (window.confirm(t('confirmDelete'))) {
      try {
        await UsersAPI.delete(id);
        setUsers(prev => prev.filter(u => u.id !== id));
      } catch (e) {
        console.error('Failed to delete user:', e);
      }
    }
  };

  const handleToggleStatus = async (id: string) => {
    const user = users.find(u => u.id === id);
    if (!user) return;
    const newStatus = user.status === 'Active' ? 'Inactive' : 'Active';
    try {
      const updated = await UsersAPI.update(id, { status: newStatus });
      setUsers(prev => prev.map(u => u.id === id ? updated : u));
    } catch (e) {
      console.error('Failed to toggle user status:', e);
    }
  };

  return (
    <div className="p-6 space-y-6 h-full overflow-y-auto">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-white">{t('users')}</h2>
          <p className="text-sm text-zinc-500">Manage system access roles and account status.</p>
        </div>
        <button onClick={handleOpenAddModal} className="flex items-center space-x-2 rtl:space-x-reverse px-4 py-2 bg-vs-orange text-black rounded hover:bg-vs-lightOrange text-sm font-bold shadow-glow transition-colors">
            <Plus size={18} />
            <span>{t('addUser')}</span>
        </button>
      </div>

      <div className="bg-[#0f0f11] border border-zinc-800 rounded-xl shadow-sm overflow-hidden">
        <table className="w-full text-start text-sm text-zinc-400">
          <thead className="bg-zinc-900/50 text-zinc-500 uppercase text-xs font-semibold border-b border-zinc-800">
            <tr>
              <th className="px-6 py-4 text-start">User</th>
              <th className="px-6 py-4 text-start">Role</th>
              <th className="px-6 py-4 text-start">{t('status')}</th>
              <th className="px-6 py-4 text-start">Last Active</th>
              <th className="px-6 py-4 text-end">{t('action')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/50">
            {users.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-12 text-center text-zinc-500">
                  <p className="text-sm">{t('noResults')}</p>
                </td>
              </tr>
            ) : (
              users.map((user) => (
              <tr key={user.id} className="hover:bg-zinc-900/30 transition-colors group">
                <td className="px-6 py-4">
                  <div className="flex items-center space-x-3 rtl:space-x-reverse">
                    <div className="w-10 h-10 bg-zinc-800 rounded-full flex items-center justify-center text-zinc-500 group-hover:bg-vs-orange/20 group-hover:text-vs-orange transition-colors">
                       <UserIcon size={20} />
                    </div>
                    <div>
                      <p className="font-semibold text-white">{user.name}</p>
                      <p className="text-xs text-zinc-500">{user.email}</p>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center text-zinc-300 font-medium">
                    <Shield size={14} className="me-2 text-vs-orange" />
                    {t(user.role.toLowerCase().replace(/ /g, '') as any)}
                  </div>
                </td>
                <td className="px-6 py-4">
                  <button 
                    onClick={() => handleToggleStatus(user.id)}
                    className={`px-2 py-1 rounded-full text-xs font-semibold cursor-pointer hover:opacity-80 transition-opacity ${
                      user.status === 'Active' ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20' : 'bg-zinc-800 text-zinc-500 border border-zinc-700'
                    }`}
                  >
                    {t(user.status.toLowerCase() as any)}
                  </button>
                </td>
                <td className="px-6 py-4 text-zinc-500 font-mono text-xs">
                  2 hours ago
                </td>
                <td className="px-6 py-4 text-end">
                  <div className="flex items-center justify-end space-x-1 rtl:space-x-reverse">
                    <button 
                      onClick={() => handleOpenEditModal(user)} 
                      className="text-zinc-500 hover:text-white p-2 rounded-full hover:bg-zinc-800 transition-colors"
                      title={t('edit')}
                    >
                      <Edit2 size={16} />
                    </button>
                    <button 
                      onClick={() => handleDeleteUser(user.id)} 
                      className="text-zinc-500 hover:text-red-400 p-2 rounded-full hover:bg-red-500/10 transition-colors"
                      title={t('delete')}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </td>
              </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-[#0f0f11] border border-zinc-800 rounded-2xl w-full max-w-md overflow-hidden shadow-2xl animate-in zoom-in-95 duration-200">
            <div className="p-6 border-b border-zinc-800 flex justify-between items-center bg-zinc-900/20">
              <h3 className="text-lg font-bold text-white uppercase tracking-wider">
                {editingUser ? t('edit') + ' User' : t('addUser')}
              </h3>
              <button onClick={() => { setShowAddModal(false); resetForm(); }} className="text-zinc-500 hover:text-white transition-colors">
                <X size={24} />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div className="space-y-2">
                <label className="text-xs font-bold text-zinc-500 uppercase">Full Name *</label>
                <input 
                  type="text" 
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="w-full bg-black border border-zinc-800 rounded-lg p-3 text-white focus:border-vs-orange outline-none" 
                  placeholder="John Doe" 
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs font-bold text-zinc-500 uppercase">Email Address *</label>
                <input 
                  type="email" 
                  value={formEmail}
                  onChange={(e) => setFormEmail(e.target.value)}
                  className="w-full bg-black border border-zinc-800 rounded-lg p-3 text-white focus:border-vs-orange outline-none" 
                  placeholder="john@visionsafe.co" 
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs font-bold text-zinc-500 uppercase">System Role</label>
                <select 
                  value={formRole}
                  onChange={(e) => setFormRole(e.target.value as UserRole)}
                  className="w-full bg-black border border-zinc-800 rounded-lg p-3 text-white focus:border-vs-orange outline-none"
                >
                  <option value="Safety Engineer">Safety Engineer</option>
                  <option value="Data Analyst">Data Analyst</option>
                  <option value="Admin">Admin</option>
                </select>
              </div>
            </div>
            <div className="p-6 bg-zinc-900/30 flex justify-end space-x-3 rtl:space-x-reverse">
              <button onClick={() => { setShowAddModal(false); resetForm(); }} className="px-4 py-2 text-zinc-500 hover:text-white font-medium uppercase text-xs tracking-widest">{t('cancel')}</button>
              <button 
                onClick={handleSaveUser}
                disabled={!formName.trim() || !formEmail.trim()}
                className="px-6 py-2 bg-vs-orange text-black font-bold rounded-lg shadow-glow hover:bg-vs-lightOrange transition-colors flex items-center space-x-2 rtl:space-x-reverse uppercase text-xs tracking-widest disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <CheckCircle2 size={16} />
                <span>{editingUser ? t('saveChanges') : t('submit')}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default UserManagement;
