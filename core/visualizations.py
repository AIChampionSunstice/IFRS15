import plotly.graph_objects as go
import plotly.express as px
from typing import List, Dict
import pandas as pd

class IFRS15Visualizer:
    @staticmethod
    def create_agi_gauge(agi_percentage: float, threshold: float) -> go.Figure:
        color = "#10b981" if agi_percentage <= threshold else "#ef4444"
        
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=agi_percentage,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "AGI vs TCV (%)", 'font': {'size': 20}},
            delta={'reference': threshold, 'increasing': {'color': "#ef4444"}},
            gauge={
                'axis': {'range': [None, 100], 'tickwidth': 1},
                'bar': {'color': color},
                'bgcolor': "white",
                'borderwidth': 2,
                'bordercolor': "#e5e7eb",
                'steps': [
                    {'range': [0, threshold], 'color': '#d1fae5'},
                    {'range': [threshold, 100], 'color': '#fee2e2'}
                ],
                'threshold': {
                    'line': {'color': "#3b82f6", 'width': 4},
                    'thickness': 0.75,
                    'value': threshold
                }
            }
        ))
        
        fig.update_layout(
            height=250,
            margin=dict(l=20, r=20, t=60, b=20),
            paper_bgcolor="white",
            font={'family': "Inter, sans-serif"}
        )
        
        return fig
    
    @staticmethod
    def create_contract_timeline(contracts: List[Dict]) -> go.Figure:
        if not contracts:
            return go.Figure()
        
        df = pd.DataFrame(contracts)
        
        fig = go.Figure()
        
        for idx, row in df.iterrows():
            client = row.get('Client Name', f'Contrat {idx}')
            start_date = row.get('SAAS START Date', '')
            contract_time = row.get('Contract Time', '')
            
            fig.add_trace(go.Scatter(
                x=[start_date],
                y=[client],
                mode='markers',
                marker=dict(size=12, color='#3b82f6'),
                name=client,
                hovertemplate=f"<b>{client}</b><br>Début: {start_date}<br>Durée: {contract_time}<extra></extra>"
            ))
        
        fig.update_layout(
            title="Timeline des contrats",
            xaxis_title="Date de début",
            yaxis_title="Client",
            height=400,
            hovermode='closest',
            showlegend=False,
            paper_bgcolor="white",
            plot_bgcolor="#f9fafb"
        )
        
        return fig
    
    @staticmethod
    def create_revenue_distribution(contracts: List[Dict]) -> go.Figure:
        if not contracts:
            return go.Figure()
        
        df = pd.DataFrame(contracts)
        
        if 'Ramp up price euros vs TCV' not in df.columns:
            return go.Figure()
        
        fig = px.bar(
            df,
            x='Client Name',
            y='Ramp up price euros vs TCV',
            title="Distribution des montants de Ramp-up (€)",
            labels={'Ramp up price euros vs TCV': 'Montant (€)', 'Client Name': 'Client'},
            color='Ramp up price euros vs TCV',
            color_continuous_scale='Blues'
        )
        
        fig.update_layout(
            height=400,
            paper_bgcolor="white",
            plot_bgcolor="#f9fafb",
            showlegend=False
        )
        
        return fig
    
    @staticmethod
    def create_ifrs15_compliance_pie(contracts: List[Dict]) -> go.Figure:
        if not contracts:
            return go.Figure()
        
        df = pd.DataFrame(contracts)
        
        if 'IFRS 15 Agi' not in df.columns:
            return go.Figure()
        
        compliance_counts = df['IFRS 15 Agi'].value_counts()
        
        colors = {'Yes': '#10b981', 'No': '#ef4444'}
        
        fig = go.Figure(data=[go.Pie(
            labels=compliance_counts.index,
            values=compliance_counts.values,
            marker=dict(colors=[colors.get(label, '#6b7280') for label in compliance_counts.index]),
            hole=0.4,
            textinfo='label+percent',
            hovertemplate='<b>%{label}</b><br>Contrats: %{value}<br>Pourcentage: %{percent}<extra></extra>'
        )])
        
        fig.update_layout(
            title="Conformité IFRS15 AGI",
            height=350,
            paper_bgcolor="white",
            annotations=[dict(text='IFRS15', x=0.5, y=0.5, font_size=20, showarrow=False)]
        )
        
        return fig
    
    @staticmethod
    def create_summary_metrics(contracts: List[Dict]) -> Dict:
        if not contracts:
            return {
                'total_contracts': 0,
                'compliant_contracts': 0,
                'total_tcv': 0,
                'compliance_rate': 0
            }
        
        df = pd.DataFrame(contracts)
        
        total = len(df)
        compliant = len(df[df.get('IFRS 15 Agi', 'No') == 'Yes']) if 'IFRS 15 Agi' in df.columns else 0
        total_tcv = df['Ramp up price euros vs TCV'].sum() if 'Ramp up price euros vs TCV' in df.columns else 0
        
        return {
            'total_contracts': total,
            'compliant_contracts': compliant,
            'total_tcv': total_tcv,
            'compliance_rate': (compliant / total * 100) if total > 0 else 0
        }